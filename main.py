import json
import logging
import os
import uuid
# import redis
from typing import List, Dict

from agent_builder.agent_factory import AgentCard, AgentSkill
from agent_builder.resource_registry import ExecutableResourceRegistry, ResourceRegistry
from agent_builder.agent import Agent, prompt_adaptor
from agent_builder.agent_language_builder import AgentFunctionCallingActionLanguage
from agent_builder.environment_builder import Environment
from agent_builder.memory_builder import Memory, PayloadMemory
from utils.llm_api import infer_llm_generation

from agent_builder.agent import Agent

from agent_builder.tools_factory import ToolsFactory
from utils.prompt_store import PromptStore
from utils.util import initialize_logging

from tools_repository.people_org_agent.run import fetch_people_org_response
from utils.util import make_fastapi_request, initialize_logging

logger = logging.getLogger('agent_log')
initialize_logging(logger)


PAYLOAD_MEMORY = PayloadMemory()


GENERATE_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {
            "type": "string",
            "description": "All the information the agent has gathered so far, serialized as JSON or plain text."
        },
        "directions": {
            "type": "string",
            "description": "Instructions on what to generate."
        }
    },
    "required": ["content", "directions"]
}


def main():
    # id = str(uuid.uuid4())
    chatbot_tools_factory = ToolsFactory()
    chatbot_register_tool = chatbot_tools_factory.register_tool
    chatbot_router = prompt_adaptor(chatbot_tools_factory)
    chatbot_selector = prompt_adaptor(chatbot_tools_factory, task="selection")

    @chatbot_register_tool(tags=["file_operations", "read"])
    def read_project_file(name: str) -> str:
        """Reads and returns the content of a specified project file.

        Opens the file in read mode and returns its entire contents as a string.
        Raises FileNotFoundError if the file doesn't exist.

        Args:
            name: The name of the file to read

        Returns:
            The contents of the file as a string
        """
        with open(name, "r") as f:
            return f.read()

    @chatbot_register_tool(tags=["data_retrieval", "people_table", "org_table"])
    def people_org_response(query: str) -> str:
        """Queries the People and Organization data repository and returns a response.

        Args:
            query: Query of the user

        Returns:
            Response as a string
        """
        return fetch_people_org_response(query=query)

    @chatbot_register_tool(tags=["file_operations", "list"])
    def list_project_files() -> List[str]:
        """Lists all Python files in the current project directory.

        Scans the current directory and returns a sorted list of all files
        that end with '.py'.

        Returns:
            A sorted list of Python filenames
        """
        return sorted([file for file in os.listdir(".")
                       if file.endswith(".py")])

    @chatbot_register_tool(
        tags=["generate", "additional information"],
    )
    def generate_content(content: str, directions: str, payload_id: str) -> str:
        """
        Given 'directions', 'content' and 'payload_id'(all string types) return the generated text.
        'payload_id' contains string type id that reference information in a memory store, to be used as context while generating content.
        """
        data = []
        if payload_id:
            data.append({
                "payload": PAYLOAD_MEMORY.retrieve_payload(payload_id)
            })
        from utils.llm_api import infer_llm_generation
        prompt = (
            f"Directions: {directions}\nContent: {content}\nContext: {data}\n"
        )
        return infer_llm_generation(prompt)

    @chatbot_register_tool(tags=["chatbot_terminate"], terminal=True)
    def chatbot_terminate(message: str) -> str:
        """Terminates the agent's execution with a final message.

        Args:
            message: The final message to return before terminating

        Returns:
            The final message to return before terminating
        """
        return f"{message}\nTerminating..."

    news_events_tools_factory = ToolsFactory()
    news_events_register_tool = news_events_tools_factory.register_tool
    news_events_router = prompt_adaptor(news_events_tools_factory)
    news_events_selector = prompt_adaptor(news_events_tools_factory, task="selection")

    @news_events_register_tool(tags=["data_retrieval", "news_and_events"])
    def news_and_events_response(query: str) -> str:
        """Queries the News and Events data repository and returns a response.

        Args:
            query: Query of the user

        Returns:
            Response as a string
        """
        url = f'http://192.168.49.1:8020/api/search_and_recommendation'
        # url = f'http://10.3.7.166:8020/api/search_and_recommendation'

        payload = {
            "query": query
        }
        result = make_fastapi_request(url, logger, method="POST", params=payload)
        return result

    @news_events_register_tool(
        tags=["generate", "additional information"],
    )
    def generate_content(content: str, directions: str, payload_id: str) -> str:
        """
        Given 'directions', 'content' and 'payload_id'(all string types) return the generated text.
        'payload_id' contains string type id that reference information in a memory store, to be used as context while generating content.
        """
        data = []
        if payload_id:
            data.append({
                "payload": PAYLOAD_MEMORY.retrieve_payload(payload_id)
            })
        from utils.llm_api import infer_llm_generation
        prompt = (
            f"Directions: {directions}\nContent: {content}\nContext: {data}\n"
        )
        return infer_llm_generation(prompt)

    @news_events_register_tool(tags=["news_and_events_terminate"], terminal=True)
    def news_and_events_terminate(message: str) -> str:
        """Terminates the agent's execution with a final message.

        Args:
            message: The final message to return before terminating

        Returns:
            The final message to return before terminating
        """
        return f"{message}\nTerminating..."

    news_events_persona = "I am a focused news analysis agent. I specialize in retrieving the most relevant news articles based on your query, summarizing key developments, and presenting structured, informative responses grounded in real information."
    news_events_description = "A domain-aware information retrieval agent that searches a news repository, filters articles based on query relevance, and returns both a synthesized response and the matched articles. Ideal for surfacing recent events, identifying trends, or providing evidence-backed insights."
    news_events_skills = [AgentSkill(
        id=str(uuid.uuid4()),
        name="Fetch News and Articles",
        description=(
            "Handles natural language queries related to current events or recent developments. "
            "Retrieves relevant news articles from the internal repository and generates a synthesized summary "
            "alongside the article data. Ideal for surfacing timely insights from real-world sources."
        ),
        tags=["news", "events", "data retrieval", "summarization", "agent"],
        examples=[
            "User: What are the latest updates on AI regulation in Europe?\n→ Retrieves and summarizes top articles from the news repository.",
            "User: Show me recent funding announcements in the biotech sector.\n→ Fetches and summarizes related articles.",
            "User: What's trending in tech this week?\n→ Returns summarized highlights from relevant news sources."
        ]
    )]
    news_events_card = AgentCard(name="news_and_events", persona=news_events_persona,
                                 description=news_events_description,
                                 skills=news_events_skills, version="1", url="")

    news_events_agent = Agent(
        agent_card=news_events_card,
        agent_language=AgentFunctionCallingActionLanguage(),
        resources=ExecutableResourceRegistry(tools_factory=news_events_tools_factory,
                                             tags=["data_retrieval", "news_and_events", "generate", "additional information", "news_and_events_terminate"]),
        generate_response_routing=news_events_router,
        generate_response_tool_selection=news_events_selector,
        generate_response=infer_llm_generation,
        environment=Environment(),
        payload_memory=PAYLOAD_MEMORY
    )


    chatbot_persona = "You are a thoughtful AI coordinator. You break down user goals, recall past context, and decide whether to act directly or delegate to a specialized agent — always choosing the most effective path forward to accomplish the task, using the goals as a rough guideline."
    chatbot_description = "A reasoning-based AI orchestrator that intelligently selects the right agent or action to complete complex tasks using goals, memory, and tools."
    chatbot_skills = [AgentSkill(
        id=str(uuid.uuid4()),
        name="Routing",
        description=(
            "Interprets natural language user input and determines whether to call a tool "
            "or delegate to a specialized agent. Uses goals, memory, and context to select the best next action."
        ),
        tags=["chatbot", "orchestration", "routing", "llm", "function-calling", "generate", "additional information"],
        examples=[
            "User: What files are in the directory?\n→ Action: list_project_files",
            "User: Summarize key org changes.\n→ Action: people_org_response",
            "User: Create a paragraph about our mission.\n→ Action: generate_content",
            "User: We're done here.\n→ Tool: terminate"
        ]
    )]
    chatbot_card = AgentCard(name="Chatbot", persona=chatbot_persona, description=chatbot_description,
                             skills=chatbot_skills, version="1", url="")

    chat_agent = Agent(
        agent_card=chatbot_card,
        agent_language=AgentFunctionCallingActionLanguage(),
        resources=ExecutableResourceRegistry(tools_factory=chatbot_tools_factory,
                                             agents=[news_events_agent.agent_context],
                                             tags=["file_operations", "generate", "chatbot_terminate", "data_retrieval"]),
        generate_response_routing=chatbot_router,
        generate_response_tool_selection=chatbot_selector,
        generate_response=infer_llm_generation,
        environment=Environment(),
        payload_memory=PAYLOAD_MEMORY
    )

    # for i in range(100):
    #     final_memory = agent.run(user_input)
    #     print(final_memory.get_memories())
    #     print(f"\n\n************************\nRan {i+1} iterations successfully!!\n\n")

    memory = Memory()

    while True:
        print("=== Question ===")
        query = input(">>> ")
        if query.lower() == "exit":
            break
        final_response = chat_agent.run(query, memory=memory)
        # final_response = json.loads(final_memory.get_memories()[-1]["content"])["result"]
        print("\n=== RESPONSE ===:\n", final_response)


if __name__ == "__main__":
    main()
