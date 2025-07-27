import os
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated, List
import operator
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage, ChatMessage

memory = SqliteSaver.from_conn_string(":memory:")

LANGCHAIN_API_KEY="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"
LANGCHAIN_TRACING_V2="true"

os.environ[
    "OPENAI_API_KEY"] = "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"



class AgentState(TypedDict):
    task: str
    plan: str
    draft: str
    critique: str
    content: List[str]
    revision_number: int
    max_revisions: int

from langchain_openai import ChatOpenAI
model = ChatOpenAI(model="gpt-4o", temperature=0)

PLAN_PROMPT = """
    
"""


