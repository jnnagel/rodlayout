_handle_part_y = [
    ('top', 'upper'),
    ('bottom', 'lower'),
    ('center', 'center'),
]
_handle_part_x = ['left', 'center', 'right']

python_skill_handle = {
    # Designed to use the same handles as the simple geometry package.
    f'{py}_{x}': f'{sy}{x.title()}'
    for py, sy in _handle_part_y
    for x in _handle_part_x
}
