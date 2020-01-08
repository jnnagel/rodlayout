_handle_part_y = [
    ('top', 'upper'),
    ('upper', 'upper'),
    ('bottom', 'lower'),
    ('lower', 'lower'),
    ('center', 'center'),
]
_handle_part_x = ['left', 'center', 'right']

python_skill_handle = {
    f'{py}_{x}': f'{sy}{x.title()}' for py, sy in _handle_part_y for x in _handle_part_x
}

for x in _handle_part_x:
    python_skill_handle[x] = 'center' + x.title()

for py, sy in _handle_part_y:
    python_skill_handle[py] = sy + 'Center'
