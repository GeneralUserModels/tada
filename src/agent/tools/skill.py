import re
from pathlib import Path

from .base_tool import BaseTool


class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills = {}
        if not skills_dir.exists():
            return
        for f in sorted(skills_dir.rglob("SKILL.md")):
            text = f.read_text()
            match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
            meta, body = {}, text
            if match:
                for line in match.group(1).strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
                body = match.group(2).strip()
            name = meta.get("name", f.parent.name)
            self.skills[name] = {"meta": meta, "body": body}

    def descriptions(self) -> str:
        if not self.skills:
            return "(no skills)"
        return "\n".join(
            f"  - {n}: {s['meta'].get('description', '-')}" for n, s in self.skills.items()
        )

    def load(self, name: str) -> str:
        s = self.skills.get(name)
        if not s:
            return f"Error: Unknown skill '{name}'. Available: {', '.join(self.skills.keys())}"
        return f"<skill name=\"{name}\">\n{s['body']}\n</skill>"


class SkillTool(BaseTool):
    def __init__(self, loader: SkillLoader):
        super().__init__("load_skill", "Load specialized knowledge by name.",
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the skill to load"}
                },
                "required": ["name"]
            }
        )
        self._loader = loader

    def run(self, name: str):
        return self._loader.load(name)
