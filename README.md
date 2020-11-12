# Endless sky mission graph

pip requirements

    endless-sky-parser

Other requirements

    graphviz

This was the command used to generate the SVG files (on Linux. Windows users might have to do something different)

    cat <endless-sky-path>/data/*.txt  <endless-sky-path>/data/*/*.txt | python3.7 -m endless_sky_grapher > test.gv
    dot -Tsvg test.gv > test.svg

