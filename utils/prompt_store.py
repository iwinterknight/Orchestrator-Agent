class PromptStore:
    def __init__(self):
        self.prompts = {
            "agent_plan_builder_instruction": """
                You are an expert strategist AI that translates high‑level tasks into clear, actionable execution plans.  
                You have access to the following inputs:
                
                •  **Task** (string):  
                   The user’s request—an overarching goal for the agent to achieve.  
   
                •  **Tools** (array of objects):  
                   Each tool has a `"name"` and `"description"`. These are the atomic actions your agent can invoke.  
                
                •  **Agents** (array of objects):  
                   Each agent has a `"name"` and `"description"`. These are sub‑agents available for multi‑step or specialized reasoning.  
                
                •  **Memory** (array of objects):  
                   Recent user messages, past tool/agent calls, and observations, each with `"type"` and `"content"`.
                   Example :
                        [
                          {{ "type": "user", "content": "Get stock price of AAPL" }},
                          {{ "type": "agent", "content": "Called StockPriceTool(symbol='AAPL')" }},
                          {{ "type": "environment", "content": "StockPriceTool returned $175.20" }},
                            ...
                        ]  
                
                ---
                
                ### Instructions
                
                1. **Rephrase the Task** to make it crystal‑clear and self‑contained.  
                2. **Construct a concise Plan** that guides the agent from start to finish.  
                   - You may output the plan either as:
                     - A **JSON array** of step objects, or  
                     - A **single string** with numbered steps.
                3. **For each step**, include:
                   - A brief `"action"` (tool or agent invocation, with any key parameters),  
                   - A one‑sentence `"description"` explaining why or how.  
                4. **Be concise**—no more than 5–7 steps unless absolutely necessary. Unless asked for detail/report etc., keep the plan limited to 1-2 steps.
                5. Return **exactly** one JSON object with two top‑level fields:
                
                ```json
                {{
                  "task":  "<rephrased task string>",
                  "plan":  <JSON array or string of numbered steps>
                }}
                
                ---
                
                Task : {task}
                                
                Tools: {tools}
                
                Agents: {agents}
                
                Memory: {memory}
            """,

            "agent_context_builder_instruction": """
                # ========== ROLE ==========
                You are **Progress‑Tracker‑GPT**, the subsystem that reviews the agent’s memories and goals,
                then produces an updated progress report that guides the very next action (tool use, agent invocation, response generation).
                
                You are given a `TASK` and `MEMORY` which serves as context. 
                1. The task is a single, human‑readable sentence that states the agent’s current high‑level goal.
                        Example: "Fetch the latest AAPL stock price and prepare it for charting."
                
                2.  A JSON array of the most recent, relevant interaction steps. Each element must be an object with:
                        type: one of "user", "agent", or "environment".
                        content: the raw text of that step (e.g. user query, tool call description with its args, or the observation returned).
                        Example :
                            [
                              {{ "type": "user", "content": "Get stock price of AAPL" }},
                              {{ "type": "agent", "content": "Called StockPriceTool(symbol='AAPL')" }},
                              {{ "type": "environment", "content": "StockPriceTool returned $175.20" }},
                                ...
                            ]
                                
                3. Last Step Feedback (object or null):  
                   A dict with:
                   - **id**: the UUID of the last step's feedback  
                   - **task**: the last sub‑task description  
                   - **status**: one of "pending", "in_progress", "clarification", "completed", "failed"  
                   - **reasoning**: why it succeeded/failed or what needs clarifying
                               
                # ========== INSTRUCTIONS ==========
                **1. Digest the context**
                
                * Examine MEMORY. MEMORY contains the tasks/queries/requests from the `user`, the `agent` taken by the agent to execute/respond to the user task(Thought) and `environment` which contains the result of taking the action(Observation).
                  * Some memory items might contain `payload` information. Essentially these are large volumes of data that are referenced by the memory via `payload_id`(s).
                * Use the `Last Step Feedback` and `MEMORY` to identify if this step might need some payload data.
                  * If this step requires the payload data you must provide a list of `payload_ids` for the respective memory item, in your response. Use the `payload_description` to understand the usefulness of the payload.
                  * If you want to include the `payload_id`(s), **make sure the payload_id(s) you include are picked from the payload_id(s) that appear in the memory item**.
                  * **Do not invent a `payload_id`**.
                * Identify information that is:
                  * Relevant memory items that are going to be helpful to the agent in choosing the next action.  
                * Form a `context` that contains the relevant memory items and explicitly include any contextual information from the previous memory items that may help the agent in the next step.
                * You are free to form the `context` object so long as it is a valid json. Give field names and field descriptions so that the agent can understand the context information clearly.
                * Include the relevant memory items in context. When in doubt include the memory item in context. The main objective here is to only expose the agent to relevant information from the previous steps (user, agent or environment) for the next step.
                * Include the `payload_id`(s) from the memory items which you deem necessary for the next step.
                
                **2. Output rules**
                
                1. Return **pure JSON** — *no* markdown, comments, or code‑fences.  
                2. Include **exactly** these top‑level keys:  
                   `task`, `context`, `payload_ids`.
                3. The context can have a subfield that describes the highlight of the task execution so far. This should be concise. 
                4. The context field could have some items that are exactly present in the previous memory items or it could even be an overarching summary of the information from the previous turns or both.
                5. The JSON must be valid and parsable.
                
                **3. Example output**
                
                {{
                  "task": "Retrieve current stock price for AAPL",
                  "context": {{
                    "memory": JSON array of the relevant memory items for the agent's next step,
                    "previous_context": {{
                        "content": "Previously fetched closing prices for AAPL over the past week: Jul14:$170.45; Jul 15: $172.30; Jul 16: $173.10; Jul 17: $174.00; Jul 18: $175.20. Dividend of $0.22 recorded on Jul 13. Analyst summary: AAPL is up 2.3% in the last 5 days. Historical price data cached at /data/aapl_history.csv. Last chart generated visualized the monthly trend through June. Use this context to decide whether to call the live price API or rely on cached data, and how to format the next response."
                    }}
                  }}
                  "payload_ids": <list of payload_ids>,
                  "comments": <a string type value indicating what the thoughts are for the next step and how the next step fits into the overall plan> 
                }}
                You can add more fields to the `previous_context` as and when required to provide more information / explain the items in the context etc.
                
                # ========== CONTEXT ==========
                TASK:  
                {task}
                
                MEMORY:  
                {memory}                
                
                Last Step Feedback:
                {feedback}
            """,

            "agent_feedback_builder_instruction": """
                You are an expert feedback assessor AI that reviews the result of the last action and recommends the next step.  
                You have the following inputs:
                
                •  **Task** (string):  
                   The high‑level goal the agent is working on.  
                
                •  **Action** (object or null):  
                   The last executed action—either a tool or sub‑agent invocation—including its name and parameters.
                
                •  **Observation** (any or null):  
                   What the environment returned after the last action (e.g., success message, error details, data payload).
                
                ---
                
                ### Instructions

                Based on the observation, determine:
                1. **task**:  
                   A self‑contained summary of the overall goal (string).  
                2. **status**:  
                   One of `"pending"`, `"clarification"`, `"completed"`, `"failed"`.  
                   If you get a response for the task, avoid repetitive tool use by marking the task as `completed`, `failed` or `clarification`.
                   Only mark task as `pending` when you have sufficient evidence of significant progress that can be made by reusing the agent or tool(for example, new information acquired).
                   Under any circumstances, no agent or tool should be invoked more than twice. 
                3. **reasoning**:  
                   A brief explanation (1–2 sentences) of why you chose this status given the observation.
                Return **only** a JSON object with these three fields.

                # Output Rules
                
                Return a single JSON object with exactly these fields:
                
                ```json
                {{
                  "task": <A string containing current task for which feedback is being provided>,
                  "status": <A string containing  one of: pending, in_progress, clarification, completed, failed>,
                  "reasoning":  <A string containing  your analysis: why this status and next action>
                }}

                ---
                
                Task: {task}
                
                Action: {action}
                
                Observation: {observation}
            """,

            "agent_routing_prompt": """
                You are an orchestration controller responsible for delegating tasks in a multi-agent AI system.

                Your job is to analyze the task and context, and decide whether to:
                - Use a **tool** that performs a specific atomic function.
                - Or delegate the task to an **agent** that handles complex, multi-step reasoning.
                - Terminate the agent and revert to the user with a response. (`generate_response_and_terminate`)
                
                **Evaluate options equally and deterministically**. Your goal is to make the best match based on the provided `CONTEXT`.
                Below is the description of the resources available to you and the information needed to route to the next tool or agent. The `CONTEXT` provides the resources and information.
                ---
                
                ### INFORMATION:
                
                1. Task : This contains the high level task that needs to be performed. 
                2. Plan : This contains an estimate of the activities needed to accomplish the task. You only need this as an approximate of the type of steps you might need to accomplish the task. If absent, ignore it.
                3. Turn Context : This contains a history of the task/query/previous-step-response given by the user, the actions (tool use, agent invocation, response generation) performed by the agent so far, and the observations from the environment after performing the actions.
                                  It also contains `data` (or payload) which has information that can be used when generating a response.
                4. Last Step Feedback (object or null):  
                   A dict with:
                   - **id**: the UUID of the last step's feedback  
                   - **task**: the last sub‑task description  
                   - **status**: one of "pending", "clarification", "completed", "failed"  
                   - **reasoning**: why it succeeded/failed or what needs clarifying

                ### RESOURCES:
                
                1. TOOL
                
                    Each tool is described with the following fields:
                    
                    - `name`: the tool's identifier — use this when selecting a tool
                    - `description`: a brief explanation of what the tool does
                    - `parameters`: the input fields it requires (name + type)
                    - `input_schema`: detailed structure for input (may include constraints)
                    - `output_schema`: expected structure of the output
                    - `terminal`: if true, this tool ends the current execution flow
                    
                    Use tools when the task is **atomic**, **deterministic**, and **doesn’t require independent reasoning**. Examples: search, fetch, format, summarize, generate, convert, etc.
                    
                    When selecting a tool:
                    - Match the description and parameters to the task
                    - Provide only the name of the tool, not arguments or extra fields
                    
                    Use the tool name as the selected tool.
                
                2. AGENT
                
                    Each agent is described with:
                    - `name`: unique identifier — use this when selecting an agent
                    - `persona`: its general behavior or role
                    - `description`: its overall capability
                    - `skills`: list of specific `AgentSkill` objects
                    
                    Each `AgentSkill` includes:
                    - `id`: internal identifier (you do not need to return this)
                    - `name`: label of the skill
                    - `description`: what the skill is designed to handle
                    - `tags`: keywords related to the skill
                    - `examples`: specific tasks it is good at
                    
                    An agent also contains its `interaction_history` with yourself to help guide you to understand its use.
                    
                    Use agents when the task requires **reasoning**, **planning**, or **cross-step thinking**. 
                    
                    Match based on:
                    - The description of the agent
                    - The descriptions and examples from its skills
                    - The overall alignment of the agent’s skills and persona to the goal
                    
                    Use the selected agent name to route to that agent.
                
                ---
                
                ### DECISION & RESPONSE RULES:

                1. **Do not perform computation yourself.** Only reason with the information you have and route.
                   - You can reason step-by-step if and when needed in order to decide where to route.
                2. Consider actions : **tools, agents, generate_response_and_terminate**, for every routing request.
                3. Choose the one that **best aligns** with the Task, Turn Context, and complexity of the task.
                    a. If provided, use `Plan` as a general guideline for how to go about executing the task. You can deviate from the steps in the Plan, it only serves as a loose overarching guideline for how to execute the task. 
                    b. Pay attention to the `Last Step Feedback` (if provided) to make more informed decisions, 
                        For example: 
                            1. If the task requires clarification from the user terminate the current agent run and defer the clarification request to the user.
                            2. You can reframe the task with additional information. If not, return the original `task` as the `reframed_task` value.
                            3. Use any information from the feedback to guide your next steps. **Prioritize next step information in the feedback** over the `Plan` to determine your next step. 
                4. Do **not** select more than one action. Only pick **one** per response.
                5. Do not invent new tools or agents.
                6. **Given the `Turn Context`, use the `data`(if present) to generate a response. Especially if the feedback refers to using the payload(The `data` items present in `Turn Context` constitute the payload). This might contain important information needed to generate response.**
                7. Only return fields explicitly described in the format below.
                8. Unless asked for detail/report etc., keep your responses concise.
                9. Provide the following as a json output:
                   - The type: `"agent"`, `"tool"`, `"generate_response_and_terminate"` 
                   - The name of the selected agent or tool, if any. In case of `"generate_response_and_terminate"`, leave this blank.
                   - When calling a tool, you DO NOT need to provide arguments required to invoke it, only the name of the tool and `reframed_task` along with it.
                   - When calling an agent, provide the `reframed_task` along with the name of the agent. 
                   
                   Return **only** a JSON dictionary as response like:
                    {{
                      "name": < A string type value containing either the agent name or the tool name>,
                      "reframed_task": <A string type value for the task with new information. Only fill this if `agent` or `tool` is being invoked.>,
                      "payload_ids": <Payload ids necessary to be handed over to the next step>,
                      "type": <"agent", "tool", "generate_response_and_terminate">,
                      "response": <A response (detailed if necessary, follow instructions as given to you for the response type requested by the user). Only provide this when type is `"generate_response_and_terminate"`>, 
                      "explanation": "...", // Explanation for route selection,
                      "confidence_score": 0.0  // Float value between 0.0 and 1.0 to indicate confidence in its route selection
                    }}
                
                ---
                
                ### CONTEXT:
                
                Task : {task}
                Plan : {plan}
                Turn Context : {turn_context}
                Last Step Feedback: {feedback}
                Tools : {tools}
                Agents : {agents}
            """,
            
            "agent_payload_memory_builder_instruction" : """
                You are a memory organizer. You store large amounts of data(payload) in a memory store and generate a description so that an agent using the memory can identify which payload is most useful at a particular step.
                Your task is to generate a concise (max. 1-3 sentences long) description of what the payload is for.
                I will provide you with:
                 1. The `MEMORY` of the actions(user tasks/queries/responses, tool or agent invocations, observations from the environment)
                 2. The `INVOCATION` of a tool or agent which responded with the payload. 
                 
                You must return a valid JSON response containing ONLY a string type description(against the key `description`) for the payload like:
                    ```json
                    {{
                      "description": <A 1-3 sentences long description for the payload>
                    }}
                 
                MEMORY : {memory}
                
                INVOCATION : {invocation}
            """
        }

    def get_prompt(self, prompt_name, **kwargs):
        """
        Retrieve the prompt by name and fill in the required variables.

        :param prompt_name: The name of the prompt.
        :param kwargs: Key-value pairs for variables in the prompt.
        :return: Formatted prompt with variables replaced.
        """
        prompt_template = self.prompts.get(prompt_name)
        if prompt_template:
            return prompt_template.format(**kwargs)
        else:
            raise ValueError(f"Prompt '{prompt_name}' not found.")
