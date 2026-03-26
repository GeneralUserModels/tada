
class BaseTool:
    def __init__(self, name: str, description: str, input_schema: dict):
        self.name = name
        self.description = description
        self.input_schema = input_schema

    def run(self, input: str):
        pass
    
    def render(self) -> str:
        pass