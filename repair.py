import re

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix the broken emit patterns:
text = text.replace("emit_auction_update(session.get('room_name'))\n    return jsonify", "return jsonify")
text = text.replace("emit_auction_update(session.get('room_name'))\n        return jsonify", "return jsonify")
text = text.replace("emit_auction_update(session.get('room_name'))\n    return redirect", "return redirect")
text = text.replace("emit_auction_update(session.get('room_name'))\n        return redirect", "return redirect")
text = text.replace("; emit_auction_update(session.get('room_name'))\n    return", "; return")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("Repair complete.")
