import time
import inspect
import traceback
from typing import Any

from agent_builder.resource_registry import Action, ActionContext


class Environment:
    def __has_named_parameter(self, func, param_name: str) -> bool:
        """
        Check if a function has a parameter with the given name.

        Args:
            func (Callable): The function to inspect.
            param_name (str): The parameter name to look for.

        Returns:
            bool: True if the parameter exists, False otherwise.
        """
        try:
            signature = inspect.signature(func)
            return param_name in signature.parameters
        except (TypeError, ValueError):
            # If func is not callable or signature cannot be determined
            return False

    def execute_action(self, action: Action, args: dict, action_context: ActionContext=None) -> dict:
        try:
            args_copy = args.copy()

            if action_context:
                # If the function wants action_context, provide it
                if self.__has_named_parameter(action.function, "action_context"):
                    args_copy["action_context"] = action_context

                # Inject properties from action_context that match _prefixed parameters
                for key, value in action_context.properties.items():
                    param_name = "_" + key
                    if self.__has_named_parameter(action.function, param_name):
                        args_copy[param_name] = value

            result = action.execute(**args)
            return self.format_result(result)
        except Exception as e:
            return {
                "tool_executed": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }

    def format_result(self, result: Any) -> dict:
        return {
            "tool_executed": True,
            "result": result,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z")
        }
