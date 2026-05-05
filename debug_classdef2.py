"""Debug position."""
import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider
from code_analysis.core.cst_tree.tree_builder import load_file_to_tree

FILE = 'code_analysis/commands/cst_load_file_command.py'
tree = load_file_to_tree(FILE)

wrapper = MetadataWrapper(tree.module, unsafe_skip_copy=True)
positions = wrapper.resolve(PositionProvider)

for stmt in tree.module.body:
    if isinstance(stmt, cst.ClassDef):
        pos = positions.get(stmt)
        print(f'ClassDef in body: pos={pos}')
        name = getattr(stmt.name, 'value', '?')
        print(f'  name={name}')
        print(f'  start={pos.start.line},{pos.start.column} end={pos.end.line},{pos.end.column}')
