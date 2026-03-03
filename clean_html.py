import re
with open('templates/auction.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Try to find the midpoint duplication
first_part = text[:len(text)//2]
second_part = text[len(text)//2:]

# Check if there's a clear split
parts = text.split("<!DOCTYPE html>")
if len(parts) > 2:
    print(f"File contains {len(parts)-1} DOCTYPES!")
    # Just take the first valid one + DOCTYPE
    with open('templates/auction.html', 'w', encoding='utf-8') as f:
        f.write("<!DOCTYPE html>" + parts[1])

# If no DOCTYPE, try "<html>"
parts = text.split("<html")
if len(parts) > 2:
    print(f"File contains {len(parts)-1} <html> tags!")
    with open('templates/auction.html', 'w', encoding='utf-8') as f:
        f.write("<html" + parts[1])

print("Check finished.")
