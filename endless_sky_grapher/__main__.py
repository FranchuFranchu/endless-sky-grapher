import argparse
from endless_sky.datafile import DataFile
from endless_sky.datanode import DataNode
from dataclasses import dataclass,field
from typing import List, Set
import sys
import itertools
import os
from pathlib import Path
import binascii
import re
import html
import codecs

SHOW_EVENT_CODE = False
READ_ONLY_CONDITIONS = ("random","net worth","cargo space", "passenger space", "flagship crew", "flagship required crew", "flagship bunks", "cargo attractiveness", "armament deterrence", "pirate attraction", "day", "month", "year")

def escape_token(i):
    if not len({"\t", " ", "\n"} & set(i)):
        return i
    if not len({"\""} & set(i)):
        return "\"" + i.replace("\"", "\\\"") + "\""
    else:
        return "`" + i.replace("`", "\\`") + "`"

def _f(self, tab=0):
    s = tab * "    " + " ".join([escape_token(i) for i in self.tokens]) + "\n"
    for i in self.children:
        s +=  i.__str__(tab+1)
    return s

DataNode.__str__ = _f
    

class Colors:
    EVENT = '"#88FF88"'
    MISSION = '"#EECC77"'
    OR = '"#efc9ed"'
    AND = '"#f2a991"'
    LINE_NOT = '"#EE3333"'
    LINE_HAS = '"#000000"'
    JOB = '"#9197f2"'
    EXEC_EXPRESSION = '"#b5b5b5"'
    EVAL_EXPRESSION = '"#b5b5b5"'
    VARIABLE = '"#bada55"'
    OTHER_CONDITION = '"#a5a5a5"'

GRAPHVIZ_FORMAT = """
digraph endlesssky {{
\tnode [shape=box,style=filled];
{}
}}
"""
    
def serialize_node(node: DataNode):
    return binascii.hexlify(str(node).encode("utf-8")).decode("ascii")

def recursive_listdir(path):
    return (os.path.join(dp, f) for dp, dn, fn in os.walk(path) for f in fn)



@dataclass
class MainProgram():
    graphviz: str = ""
    mentioned_variables: List[str] = field(default_factory=list)
    defined_variables: Set[str] = field(default_factory=set)
    added_special_nodes: Set[str] = field(default_factory=set)
    
    def is_terminal_value(self, token: str):
        return token.isnumeric() or token in tuple("+-*/%") or token in READ_ONLY_CONDITIONS
    
    def recursive_add_conditional_expression(self, node: DataNode, name: str, add_first: bool = True):
        # left value is always a single token
        if add_first:
            self.graphviz += f'"{node.tokens[0]}" -> "{name}";\n'
            self.mentioned_variables.append(node.tokens[0])
                
        for i in node.tokens[2:]:
            if not self.is_terminal_value(i):
                self.graphviz += f'"{i}" -> "{name}";\n'
                self.mentioned_variables.append(i)
            
    
    def recursive_add_condition_nodes(self, node: DataNode, top_destination: str):
        for i in node.children:
            if i.tokens[0] in ("or", "and"):
                if not serialize_node(node) in self.added_special_nodes:
                    self.added_special_nodes.add(serialize_node(node))
                    self.graphviz += f'\t"{serialize_node(node)}" [label="{i.tokens[0]}",fillcolor={Colors.OR if i.tokens[0] == "or" else Colors.AND}];\n'
                    self.recursive_add_condition_nodes(i, serialize_node(node))
                self.graphviz += f'\t"{serialize_node(node)}" -> "{top_destination}";\n'
            elif i.tokens[0] in ("has","not"):
                m = re.match(r"(.+): (active|offered|declined|failed)", i.tokens[1])
                if m:
                    self.mentioned_variables.append(i.tokens[1].split(f": {m.group(2)}")[0])
                    self.graphviz += f'\t"{m.group(1)}" -> "{top_destination}" [label="{m.group(2)}",style=dashed,color={Colors.LINE_HAS if i.tokens[0] == "has" else Colors.LINE_NOT}];\n'
                elif re.match(r"(.+): (done)", i.tokens[1]):
                    self.graphviz += f'\t"{i.tokens[1].split(": done")[0]}" -> "{top_destination}" [color={Colors.LINE_HAS if i.tokens[0] == "has" else Colors.LINE_NOT}];\n'
                    self.mentioned_variables.append(i.tokens[1].split(": done")[0])
                        
                else:
                    self.graphviz += f'\t"{i.tokens[1]}" -> "{top_destination}" [color={Colors.LINE_HAS if i.tokens[0] == "has" else Colors.LINE_NOT}];\n'
                    self.mentioned_variables.append(i.tokens[1])
            else:
                # A condition
                node_name = f'{" ".join(i.tokens)}_{top_destination}'.replace('"', '\\"')
                self.graphviz += f'\t"{node_name}" [label="{" ".join(i.tokens)}",color={Colors.EVAL_EXPRESSION}];\n'
                self.graphviz += f'\t"{node_name}" -> "{top_destination}";\n'
                self.recursive_add_conditional_expression(i, f'{node_name}')


    def recursive_add_effect_nodes(self, node: DataNode, source: str):

        assert node.tokens[0] == "on"

        extra_label,edge_style = "", ""
        if node.tokens[1] != "complete":
            extra_label = "on " +node.tokens[1] + " "
            edge_style = "style=dashed,"
        
        for i in node.children:
            if i.tokens[0] == "event":

                self.graphviz += f'\t"{source}" -> "event: {i.tokens[1]}" [{edge_style}label="{extra_label}{i.tokens[2] if len(i.tokens) > 2 else ""}{("~" + str(i.tokens[3])) if len(i.tokens) > 3 else ""}"];\n'
            elif i.tokens[0] == "set":
                self.graphviz += f'\t"{source}" -> "{i.tokens[1]}" [{edge_style}label="{extra_label}"];\n'
            elif len(i.tokens) > 1 and i.tokens[1] in ("++", "--"):
                self.graphviz += f'\t"{source}" -> "{i.tokens[0]}" [{edge_style}label="{extra_label} {i.tokens[1]}"];\n'
            elif len(i.tokens) > 2 and i.tokens[1] in ("=", "+=", "-="):
                node_name = " ".join(escape_token(j) for j in i.tokens).replace('"', '\\"')
                self.graphviz += f'\t"{source}" -> "{node_name}" [arrowhead=none];\n'
                if node_name not in self.added_special_nodes:
                    self.graphviz += f'"{node_name}" [label="{extra_label} {node_name}", fixedsize="false", width=0, height=0,color={Colors.EXEC_EXPRESSION}];'
                    self.graphviz += f'\t"{node_name}" -> "{i.tokens[0]}";\n'
                    self.recursive_add_conditional_expression(i, node_name, False)
                    self.added_special_nodes.add(node_name)
            
                


    def main(self):
        if self.args.input == sys.stdin or not Path(self.args.input).is_dir():
            f = DataFile(self.args.input)
            missions = f.root.filter_first("mission")
            events = f.root.filter_first("event")
        else:
            missions = []
            events = []
            for i in recursive_listdir(self.args.input):
                f = DataFile(str(Path(self.args.input) / Path(i)))
                missions.append(f.root.filter_first("mission"))
                events.append(f.root.filter_first("events"))
            missions = itertools.chain(*missions)
            events = itertools.chain(*events)


        for i in missions:
            self.defined_variables.add(i.tokens[1])
            if len(list(i.filter(["job"]))):
                self.graphviz += f'\t"{i.tokens[1]}" [label="{i.tokens[1]}",fillcolor={Colors.JOB}];\n'
            else:
                self.graphviz += f'\t"{i.tokens[1]}" [label="{i.tokens[1]}",fillcolor={Colors.MISSION}];\n'

            for j in i.filter_first("name"):
                name = j.tokens[1]
            for j in i.filter(["to", "offer"]):
                self.recursive_add_condition_nodes(j, i.tokens[1])
            for j in i.filter_first("on"):
                self.recursive_add_effect_nodes(j, i.tokens[1])

        for i in events:
            self.defined_variables.add("event: " + i.tokens[1])
            if SHOW_EVENT_CODE:
                #print(str(i))
                formatted_text = html.escape("".join(str(j) for j in i.children))
                html_text = f'''{i.tokens[1]}
                <FONT FACE="Courier New" POINT-SIZE="7"><BR ALIGN=\"LEFT\"/>{formatted_text}</FONT>
                '''.replace("\n", "<BR ALIGN=\"LEFT\"/>")

                self.graphviz += f'\t"event: {i.tokens[1]}" [label=<{html_text}>,fillcolor={Colors.EVENT}];\n'
            else:
                self.graphviz += f'\t"event: {i.tokens[1]}" [label="{i.tokens[1]}",fillcolor={Colors.EVENT}];\n'



        for variable_name in self.mentioned_variables:
            if variable_name not in self.defined_variables:
                if variable_name.startswith("event: "):
                    variable_name = variable_name.split("event: ", 1)[1]
                    self.graphviz += f'\t"external event: {variable_name}" [label="external event:{variable_name}",fillcolor={Colors.EVENT}];\n'

                elif variable_name.endswith(": done"):
                    variable_name = variable_name.split(": done")[0]
                    self.graphviz += f'\t"external mission: {variable_name}" [label="external mission: {variable_name}",fillcolor={Colors.MISSION}];\n'
                else:
                    self.graphviz += f'\t"{variable_name}" [label="{variable_name}",fillcolor={Colors.VARIABLE}];\n'

        self.graphviz = GRAPHVIZ_FORMAT.format(self.graphviz)            

    @classmethod
    def run(cls):
        self = cls()

        parser = argparse.ArgumentParser()
        parser.add_argument("-i", "--input", nargs="?", default=None)
        parser.add_argument("-o", "--output", nargs="?", default=None)
        self.args = parser.parse_args()
        self.args.output = sys.stdout if self.args.output == None else open(self.args.output, "w")
        self.args.input = sys.stdin if self.args.input == None else self.args.input

        self.main()

        self.args.output.write(self.graphviz)
        self.args.output.close()
        return self


if __name__ == '__main__':
    MainProgram.run()