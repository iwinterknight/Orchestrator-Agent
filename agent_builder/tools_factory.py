import inspect
from typing import get_type_hints, List


class ToolsFactory:
    def __init__(self):
        self.tools = {}
        self.tools_by_tag = {}


    def get_tool_metadata(self, func, tool_name=None, description=None, parameters_override=None, terminal=False,
                          tags=None, input_schema=None, output_schema=None):
        """
           Extracts metadata for a function to use in tool registration.

           Parameters:
               func (function): The function to extract metadata from.
               tool_name (str, optional): The name of the tool. Defaults to the function name.
               description (str, optional): Description of the tool. Defaults to the function's docstring.
               parameters_override (dict, optional): Override for the argument schema. Defaults to dynamically inferred schema.
               terminal (bool, optional): Whether the tool is terminal. Defaults to False.
               tags (List[str], optional): List of tags to associate with the tool.

           Returns:
               dict: A dictionary containing metadata about the tool, including description, args schema, and the function.
        """
        tool_name = tool_name or func.__name__

        description = description or (func.__doc__.strip() if func.__doc__ else "No description provided.")

        if parameters_override is None:
            signature = inspect.signature(func)
            type_hints = get_type_hints(func)

            args_schema = {
                "type": "object",
                "properties": {},
                "required": []
            }
            for param_name, param in signature.parameters.items():

                if param_name in ["tool_context", "agent_context"] or param_name.startswith("_"):
                    continue  # Skip these parameters

                def get_json_type(param_type):
                    if param_type == str:
                        return "string"
                    elif param_type == int:
                        return "integer"
                    elif param_type == float:
                        return "number"
                    elif param_type == bool:
                        return "boolean"
                    elif param_type == list:
                        return "array"
                    elif param_type == dict:
                        return "object"
                    else:
                        return "string"

                param_type = type_hints.get(param_name, str)
                param_schema = {"type": get_json_type(param_type)}

                args_schema["properties"][param_name] = param_schema

                if param.default == inspect.Parameter.empty:
                    args_schema["required"].append(param_name)
        else:
            args_schema = parameters_override

        return {
            "tool_name": tool_name,
            "description": description,
            "parameters": args_schema,
            "function": func,
            "terminal": terminal,
            "tags": tags or [],
            "input_schema": input_schema,
            "output_schema": output_schema
        }

    def register_tool(self, tool_name=None, description=None, parameters_override=None, terminal=False, tags=None, input_schema=None, output_schema=None):
        """
        A decorator to dynamically register a function in the tools dictionary with its parameters, schema, and docstring.

        Parameters:
            tool_name (str, optional): The name of the tool to register. Defaults to the function name.
            description (str, optional): Override for the tool's description. Defaults to the function's docstring.
            parameters_override (dict, optional): Override for the argument schema. Defaults to dynamically inferred schema.
            terminal (bool, optional): Whether the tool is terminal. Defaults to False.
            tags (List[str], optional): List of tags to associate with the tool.
            input_schema (dict, optional): Input schema. Defaults to None.
            output_schema (dict, optional): Output schema. Defaults to None.

        Returns:
            function: The wrapped function.
        """

        def decorator(func):
            metadata = self.get_tool_metadata(
                func=func,
                tool_name=tool_name,
                description=description,
                parameters_override=parameters_override,
                terminal=terminal,
                tags=tags,
                input_schema=input_schema,
                output_schema=output_schema
            )

            self.tools[metadata["tool_name"]] = {
                "description": metadata["description"],
                "parameters": metadata["parameters"],
                "function": metadata["function"],
                "terminal": metadata["terminal"],
                "tags": metadata["tags"] or [],
                "input_schema": metadata["input_schema"] or None,
                "output_schema": metadata["output_schema"] or None
            }

            for tag in metadata["tags"]:
                if tag not in self.tools_by_tag:
                    self.tools_by_tag[tag] = []
                self.tools_by_tag[tag].append(metadata["tool_name"])

            return func

        return decorator

