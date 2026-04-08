from pathlib import Path

from .base_tool import BaseTool
from .read import ReadTool
from .write import WriteTool
from .edit import EditTool
from .terminal import TerminalTool
from .mcp import MCPTool
from .todo import PlanState, PlanWriteTool, PlanUpdateTool
from .subagent import SubAgentTool
from .compact import CompactTool
from .background import BackgroundManager, BackgroundRunTool, CheckBackgroundTool
from .task_manager import TaskManager, TaskCreateTool, TaskGetTool, TaskUpdateTool, TaskListTool
from .skill import SkillLoader, SkillTool
from .browser import (
    BrowserManager, BrowserNavigateTool, BrowserReadTextTool,
    BrowserClickTool, BrowserTypeTool, BrowserScreenshotTool,
)

SKILLS_DIR = Path(__file__).parent.parent / "skills"
TASKS_DIR = Path("/tmp/tada_tasks")

_bg_manager = BackgroundManager()
_task_manager = TaskManager(TASKS_DIR)
_skill_loader = SkillLoader(SKILLS_DIR)
_browser_manager = BrowserManager()

_plan_state = PlanState()

ALL_TOOLS = [
    ReadTool(), WriteTool(), EditTool(), TerminalTool(),
    PlanWriteTool(_plan_state), PlanUpdateTool(_plan_state), SkillTool(_skill_loader),
    BackgroundRunTool(_bg_manager), CheckBackgroundTool(_bg_manager),
    TaskCreateTool(_task_manager), TaskGetTool(_task_manager),
    TaskUpdateTool(_task_manager), TaskListTool(_task_manager),
    BrowserNavigateTool(_browser_manager), BrowserReadTextTool(_browser_manager),
    BrowserClickTool(_browser_manager), BrowserTypeTool(_browser_manager),
    BrowserScreenshotTool(_browser_manager),
]
TOOL_MAP = {t.name: t for t in ALL_TOOLS}


def register_mcp_servers(servers: list[dict]) -> MCPTool:
    """Connect to MCP servers and register the call_mcp tool."""
    mcp_tool = MCPTool(servers)
    mcp_tool.connect_all()
    ALL_TOOLS.append(mcp_tool)
    TOOL_MAP[mcp_tool.name] = mcp_tool
    return mcp_tool
