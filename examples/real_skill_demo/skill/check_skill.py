from pathlib import Path

content = Path("SKILL.md").read_text(encoding="utf-8")
if "Use the formal greeting." in content and "Do not use the formal greeting." not in content:
    print("formal greeting ok")
else:
    print("formal greeting missing")
