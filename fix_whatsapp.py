import re

with open('bot/whatsapp.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for i in range(len(lines)):
    line = lines[i]
    if line.startswith('        resp = '):
        if 'async with' in lines[i-1] or 'with httpx.Client' in lines[i-1]:
            line = '    ' + line
    elif line.startswith('    if resp.status_code >= 300:'):
        if 'resp = ' in lines[i-1]:
            line = '    ' + line
    elif line.startswith('        raise WhatsAppError'):
        if 'if resp.status_code >= 300:' in lines[i-1]:
            line = '    ' + line
    new_lines.append(line)

with open('bot/whatsapp.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("done")
