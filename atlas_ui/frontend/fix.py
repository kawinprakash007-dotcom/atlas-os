with open('components/UserManagement.js', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('\\${', '${').replace('\\`', '`')
with open('components/UserManagement.js', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
