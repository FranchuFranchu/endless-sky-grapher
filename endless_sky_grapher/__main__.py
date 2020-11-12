import argparse
from endless_sky.datafile import DataFile
from endless_sky.datanode import DataNode
from dataclasses import dataclass,field
from typing import List
import sys
import itertools
import os
from pathlib import Path
import binascii
import re

class Colors:
    EVENT = '"#88FF88"'
    MISSION = '"#EECC77"'
    OR = '"#efc9ed"'
    AND = '"#f2a991"'
    LINE_NOT = '"#EE3333"'
    LINE_HAS = '"#000000"'
    JOB = '"#9197f2"'

GRAPHVIZ_FORMAT = """
digraph endlesssky {{
\tnode [shape=box,style=filled];
{}
}}
"""
    
def serialize_node(node: DataNode):
    return binascii.hexlify(str(node).encode("utf-8")).decode("ascii")

@dataclass
class MainProgram():
    graphviz: str = ""

    def add_variable(self, variable_name):
        if variable_name.startswith("event: "):
            variable_name = variable_name.split("event: ", 1)[1]
            self.graphviz += f'\t"event: {variable_name}" [label="{variable_name}",fillcolor={Colors.EVENT}];\n'

        if variable_name.endswith(": done"):
            variable_name = variable_name.split(": done")[0]
            self.graphviz += f'\t"{variable_name}" [label="{variable_name}",fillcolor={Colors.MISSION}];\n'

    def recursive_add_condition_nodes(self, node: DataNode, top_destination: str):
        for i in node.children:
            if i.tokens[0] in ("or", "and"):

                self.graphviz += f'\t"{serialize_node(node)}" [label="{i.tokens[0]}",fillcolor={Colors.OR if i.tokens[0] == "or" else Colors.AND}];\n'
                self.recursive_add_condition_nodes(i, serialize_node(node))
                self.graphviz += f'\t"{serialize_node(node)}" -> "{top_destination}";\n'
            elif i.tokens[0] in ("has","not"):
                self.add_variable(i.tokens[1])
                m = re.match(r"(.+): (active|offered|declined|failed)", i.tokens[1])
                if m:
                    self.graphviz += f'\t"{m.group(1)}" -> "{top_destination}" [label="{m.group(2)}",style=dashed,color={Colors.LINE_HAS if i.tokens[0] == "has" else Colors.LINE_NOT}];\n'
                elif re.match(r"(.+): (done)", i.tokens[1]):
                    self.graphviz += f'\t"{i.tokens[1].split(": done")[0]}" -> "{top_destination}" [color={Colors.LINE_HAS if i.tokens[0] == "has" else Colors.LINE_NOT}];\n'
                        
                else:
                    self.graphviz += f'\t"{i.tokens[1]}" -> "{top_destination}" [color={Colors.LINE_HAS if i.tokens[0] == "has" else Colors.LINE_NOT}];\n'
            else:
                # A condition
                self.graphviz += f'\t"{" ".join(i.tokens)}" -> "{top_destination}";\n'


    def recursive_add_effect_nodes(self, node: DataNode, source: str):
        
        for i in node.children:
            if i.tokens[0] == "event":
                self.graphviz += f'\t"{source}" -> "event: {i.tokens[1]}";\n'
            elif i.tokens[0] == "set":
                self.graphviz += f'\t"{source}" -> "{i.tokens[1]}";\n'



    def main(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("-i", "--input", nargs="?", default=None)
        parser.add_argument("-o", "--output", nargs="?", default=None)
        args = parser.parse_args()
        args.output = sys.stdout if args.output == None else args.output
        args.input = sys.stdin if args.input == None else args.input

        if args.input == sys.stdin or not Path(args.input).is_dir():
            f = DataFile(args.input)
            missions = f.root.filter_first("mission")
        else:
            missions = []
            for i in os.listdir(args.input):
                f = DataFile(str(Path(args.input) / Path(i)))
                missions.append(f.root.filter_first("mission"))
            missions = itertools.chain(*missions)


        for i in missions:
            if len(list(i.filter(["job"]))):
                self.graphviz += f'\t"{i.tokens[1]}" [label="{i.tokens[1]}",fillcolor={Colors.JOB}];\n'
            else:
                self.add_variable(i.tokens[1] + ": done")
            for j in i.filter_first("name"):
                name = j.tokens[1]
            for j in i.filter(["to", "offer"]):
                self.recursive_add_condition_nodes(j, i.tokens[1])
            for j in i.filter(["on", "complete"]):
                self.recursive_add_effect_nodes(j, i.tokens[1])
        self.graphviz = GRAPHVIZ_FORMAT.format(self.graphviz)            

    @classmethod
    def run(cls):
        i = cls()
        i.main()
        print(i.graphviz)
        return i


if __name__ == '__main__':
    MainProgram.run()