class SchemaStore:
    def __init__(self):
        self.schemas = {
            "news_and_events": """
                ...
            """
        }

    def get_schema(self, schema_name, **kwargs):
        """
        Retrieve the schema by name and fill in the required variables.

        :param schema_name: The name of the schema.
        :param kwargs: Key-value pairs for variables in the prompt.
        :return: Formatted prompt with variables replaced.
        """
        schema_template = self.schemas.get(schema_name)
        if schema_template:
            return schema_template.format(**kwargs)
        else:
            raise ValueError(f"Schema '{schema_name}' not found.")
