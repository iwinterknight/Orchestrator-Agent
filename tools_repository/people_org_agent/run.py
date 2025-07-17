import json
import requests
import psycopg2
import re
from urllib.parse import urljoin
from typing import Optional, List, Dict, Any, Tuple
from langchain.tools import BaseTool
from langchain.schema import BaseMessage
from pydantic import BaseModel, Field, field_validator,PrivateAttr
from datetime import datetime
from tabulate import tabulate
from contextlib import contextmanager
import age

from tools_repository.people_org_agent.util import SYSTEM_PROMPT, test_tools

import os
# os.environ["OPENAI_API_KEY"] = "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"

os.environ["OPENAI_API_KEY"] = "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"


databaseConfig = {
    "dev": {
        "host" : '172.212.85.63',
        "port" : '5433',
        "database" : 'data_service_db',
        "username" : 'orbit',
        "password" : 'ai_orbit',
        "graph_api_base_url" : 'http://172.212.85.63:8001/v1',
        "api_base_url" : 'http://172.212.85.63:8000/v1',
        "api_key" : "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ls",
        "joi_url" : "https://proud-wave-04aeb250f.4.azurestaticapps.net"
    },
    "prod": {
        "host" : '172.212.85.63',
        "port" : '5433',
        "database" : 'data_service_db',
        "username" : 'orbit',
        "password" : 'ai_orbit',
        "api_base_url" : 'http://172.212.85.63:8001/v1',
        "api_key" : "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ls"
    }
}


connection = age.connect(
                host=databaseConfig['dev']['host'],
                port=databaseConfig['dev']['port'],
                database=databaseConfig['dev']['database'],
                user=databaseConfig['dev']['username'],
                password=databaseConfig['dev']['password'],
                graph='joi_knowledge_graph')
# connection.connection.close()
# if connection.connection.closed:
#     print("closed")


class DatabaseManager:
    """Handle database connections and queries"""

    def __init__(self, config: databaseConfig):
        self.config = config
        self.connection = None

    def get_connection(self):
        """Get database connection。"""
        if not self.connection or self.connection.closed:
            self.connection = psycopg2.connect(
                host=self.config['dev']['host'],
                port=self.config['dev']['port'],
                database=self.config['dev']['database'],
                user=self.config['dev']['username'],
                password=self.config['dev']['password']
            )
        return self.connection

    @contextmanager
    def get_cursor(self):
        """Context manager for database cursor"""
        conn = self.get_connection()
        cursor = None
        try:
            cursor = conn.cursor()
            yield cursor
        finally:
            if cursor:
                cursor.close()

    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute SQL query and return results"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SET statement_timeout TO 60000")
                cursor.execute(query)

                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()
                    cursor.execute("SET statement_timeout TO 0")
                    return [dict(zip(columns, row)) for row in rows]
                return []
        except psycopg2.errors.QueryCanceled:
            print(f"Query timeout after 60000ms: {query[:100]}...")
            raise ValueError(f"Query exceeded 60000ms timeout")
        except Exception as e:
            print(f"Database query error: {e}")
            raise

    def close(self):
        """Close database connection"""
        if self.connection and not self.connection.closed:
            self.connection.close()


class GraphDatabaseManager:
    """Handle database connections and queries"""

    def __init__(self, config: databaseConfig, graph_name="joi_knowledge_graph"):
        self.config = config
        self.graph_name = graph_name
        self.connection = None

    def get_connection(self):
        """Get database connection。"""
        if not self.connection or self.connection.connection.closed:
            self.connection = age.connect(
                host=self.config['dev']['host'],
                port=self.config['dev']['port'],
                database=self.config['dev']['database'],
                user=self.config['dev']['username'],
                password=self.config['dev']['password'],
                graph=self.graph_name)
        return self.connection

    def process_vertex_result(self, vertex):
        """Process a single vertex result into JSON format"""
        if hasattr(vertex, 'properties'):
            return {
                'type': 'vertex',
                'label': vertex.label if hasattr(vertex, 'label') else None,
                'properties': dict(vertex.properties)
            }
        return vertex

    def process_path_result(self, path):
        """Process a path result into JSON format"""
        result = {'type': 'path', 'elements': []}

        for element in path:
            if isinstance(element, age.models.Path):  # Handle nested path elements
                for sub_element in element:
                    if isinstance(sub_element, age.models.Vertex):  # Node
                        result['elements'].append({
                            'type': 'node',
                            'label': sub_element.label,
                            'properties': dict(sub_element.properties) if hasattr(sub_element, 'properties') else None
                        })
                    elif isinstance(sub_element, age.models.Edge):  # Relationship
                        result['elements'].append({
                            'type': 'edge',
                            'label': sub_element.label,
                            'properties': dict(sub_element.properties) if hasattr(sub_element, 'properties') else None
                        })
            else:
                if isinstance(element, age.models.Vertex):  # Node
                    result['elements'].append({
                        'type': 'node',
                        'label': element.label,
                        'properties': dict(element.properties) if hasattr(element, 'properties') else None
                    })
                elif isinstance(element, age.models.Edge):  # Relationship
                    result['elements'].append({
                        'type': 'edge',
                        'label': element.label,
                        'properties': dict(element.properties) if hasattr(element, 'properties') else None
                    })
        return result

    def rows_to_json(self, record, column_names):
        """Process multiple cols result into JSON format"""
        row_dict = dict(zip(column_names, record))

        return row_dict

    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute cypher query and return results"""
        ag = self.get_connection()
        conn = ag.connection
        with conn.cursor() as cursor:
            try:
                cursor.execute("SET LOCAL TRANSACTION READ ONLY")
                lower_query = query.lower().replace(";", "")
                clean_query = f"""SELECT * FROM ag_catalog.cypher('joi_knowledge_graph', $cypher$ {lower_query} $cypher$) AS (result ag_catalog.agtype);"""
                print(clean_query)
                cursor.execute(clean_query)

                results = []
                for record in cursor:
                    if len(record) == 1:
                        if isinstance(record, age.models.Path):
                            results.append(self.process_path_result(record[0]))
                        else:
                            results.append(self.process_vertex_result(record[0]))
                    else:
                        column_names = tuple(desc[0] for desc in cursor.description)
                        results.append(self.rows_to_json(record, column_names))

                return results
            except Exception as e:
                print(f"Database query error: {e}")
                raise
            finally:
                if conn is not None or not conn.closed:
                    conn.close()


# Tool Input Models
class QueryPostgresInput(BaseModel):
    sql_query: str = Field(description="The SELECT SQL query to execute")

    @field_validator('sql_query')
    def validate_sql_query(cls, v):
        if not v or not v.strip() or len(v) < 2:
            raise ValueError("Query cannot be empty")
        if (v[0] == "'" and v[-1] == "'") or (v[0] == '"' and v[-1] == '"') or (v[0] == '`' and v[-1] == '`'):
            clean_query = v[1:-1]
        else:
            clean_query = v

        query_lower = clean_query.strip().lower()

        # check for SELECT or WITH statements
        if not query_lower.startswith(('select', 'with')):
            print("Only SELECT and WITH queries are allowed")
            raise ValueError("Only SELECT and WITH queries are allowed")

        return v


class QueryKGInput(BaseModel):
    cypher_query: str = Field(description="The Cypher query to execute")

    @field_validator('cypher_query')
    def validate_cypher_query(cls, v):
        if not v or not v.strip():
            raise ValueError("Query cannot be empty")

        query_lower = v.strip().lower()

        # check for SELECT or WITH statements
        if 'match' not in query_lower or 'return' not in query_lower:
            raise ValueError("Cypher query must have MATCH and RETURN")
        return v


class EntityContext(BaseModel):
    entity_type: str = Field(description="Entity type, e.g., 'person' or 'org'")
    entity_id: str = Field(description="Entity ID, e.g., '123'")


class FindPathInput(BaseModel):
    source: EntityContext = Field(description="Source entity with entity_id and entity_type")
    target: EntityContext = Field(description="Target entity with entity_id and entity_type")
    ignore: List[EntityContext] = Field(default=[], description="List of entities to exclude")


class EntityStrengthInput(BaseModel):
    source: EntityContext = Field(description="Source entity with entity_id and entity_type")
    targets: List[EntityContext] = Field(description="List of target entities with entity_id and entity_type")


class NavigationInput(BaseModel):
    user_request: str = Field(description="The user's request or intent")
    entity: Optional[EntityContext] = Field(default=None, description="Optional context entity with type and ID")


class EntityIdMappingInput(BaseModel):
    entity_type: str = Field(description="Type of entity: 'org' or 'person'")
    name: str = Field(description="Name of the entity")
    email: Optional[str] = Field(default=None, description="Email address")
    linkedin: Optional[str] = Field(default=None, description="LinkedIn profile")
    website: Optional[str] = Field(default=None, description="Website URL")
    company: Optional[str] = Field(default=None, description="Company name")
    position: Optional[str] = Field(default=None, description="Job position")
    country: Optional[str] = Field(default=None, description="Country")
    state: Optional[str] = Field(default=None, description="State/region")
    city: Optional[str] = Field(default=None, description="City")
    phone: Optional[str] = Field(default=None, description="Phone number")
    facebook: Optional[str] = Field(default=None, description="Facebook profile")
    twitter: Optional[str] = Field(default=None, description="Twitter handle")


class GetTableSchemaInput(BaseModel):
    table_name: str = Field(description="Name of the table to inspect")


# Tool Implementations
class QueryPostgresTool(BaseTool):
    name: str = "query_postgres"
    description: str = "Execute a SELECT SQL query on the PostgreSQL database"
    args_schema: type[BaseModel] = QueryPostgresInput

    def __init__(self):
        super().__init__()

    def _run(self, sql_query: str, format: str = "json") -> str:
        """Execute PostgreSQL query
        Args:
            format: 'json' or 'table' - output format for LLM
        """
        try:
            db_manager = DatabaseManager(databaseConfig)
            results = db_manager.execute_query(sql_query)

            if not results:
                return "No results found"

            if format == "json":
                return results
            else:
                return self._format_table_results(results)

        except Exception as e:
            return f"Error executing query: {str(e)}"

    def _format_table_results(self, results: List[Dict]) -> str:
        """Convert query results to formatted table string"""
        if not results:
            return "Empty result set"

        # tabulate
        headers = results[0].keys()
        rows = [list(item.values()) for item in results]
        return tabulate(rows, headers=headers, tablefmt="grid")


class QueryKGTool(BaseTool):
    name: str = "query_kg"
    description: str = "Execute a read only Cypher query on the knowledge graph (Apache AGE)"
    args_schema: type[BaseModel] = QueryKGInput

    def __init__(self):
        super().__init__()
        self._db_manager = GraphDatabaseManager(databaseConfig)

    def _run(self, cypher_query: str) -> str:
        """Execute Cypher query using Apache AGE"""
        try:
            lower_cypher_query = cypher_query.lower()
            print(lower_cypher_query)
            results = self._db_manager.execute_query(lower_cypher_query)
            print(results)

            if not results:
                return "No results found"

            return results

        except Exception as e:
            return f"Error executing Cypher query: {str(e)}"


class FindPathTool(BaseTool):
    name: str = "find_path_api"
    description: str = "Find a path between two entities, optionally excluding specific nodes"
    args_schema: type[BaseModel] = FindPathInput

    def __init__(self):
        super().__init__()
        self._api_base_url = databaseConfig['dev']['graph_api_base_url']
        self._headers = {
            "Content-Type": "application/json",
            "X-API-Key": databaseConfig['dev']['api_key']
        }

    def id_mapping(self, entity: EntityContext) -> str:
        """Map entity ID to internal ID"""
        id_type = entity.entity_type
        id = entity.entity_id
        if id_type == 'person':
            return id
        else:
            return f"o_{id}"

    def _run(self, source: EntityContext, target: EntityContext, ignore: List[EntityContext] = []) -> str:
        """Find alternative path between entities"""
        try:
            src_id = self.id_mapping(source)
            dst_id = self.id_mapping(target)
            ignore_ids = []
            for entity in ignore:
                ignore_ids.append(self.id_mapping(entity))
            # Transform parameters for API
            payload = {
                "source_uid": src_id,
                "target_uid": dst_id,
                "nodes_uid": ignore_ids or []
            }
            response = requests.post(
                f"{self._api_base_url}/remove_node",
                json=payload,
                headers=self._headers,
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                return json.dumps(result, indent=2)
            else:
                return f"API Error: {response.status_code} - {response.text}"

        except Exception as e:
            return f"Error calling alternative path API: {str(e)}"


class EntityStrengthTool(BaseTool):
    name: str = "entity_strength_api"
    description: str = "Measure connection strength between entities"
    args_schema: type[BaseModel] = EntityStrengthInput

    def __init__(self):
        super().__init__()
        self._api_base_url = databaseConfig['dev']['graph_api_base_url']
        self._headers = {
            "Content-Type": "application/json",
            "X-API-Key": databaseConfig['dev']['api_key']
        }

    def id_mapping(self, entity: EntityContext) -> str:
        """Map entity ID to internal ID"""
        id_type = entity.entity_type
        id = entity.entity_id
        if id_type == 'person':
            return id
        else:
            return f"o_{id}"

    def _run(self, source: EntityContext, targets: List[EntityContext]) -> str:
        """Calculate entity strength scores"""
        try:
            src_id = self.id_mapping(source)
            node_ids = []
            for entity in targets:
                node_ids.append({"items": [src_id, self.id_mapping(entity)]})
            print(node_ids)
            # Transform parameters for API
            payload = {
                "tuples": node_ids
            }
            print(payload)
            response = requests.post(
                f"{self._api_base_url}/conn_strength",
                json=payload,
                headers=self._headers,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                return json.dumps(result, indent=2)
            else:
                return f"API Error: {response.status_code} - {response.text}"

        except Exception as e:
            return f"Error calling entity strength API: {str(e)}"


class NavigationTool(BaseTool):
    name: str = "navigation_api"
    description: str = "Suggest relevant page and instructions based on user request"
    args_schema: type[BaseModel] = NavigationInput
    _navigation_mapping: dict = PrivateAttr()

    def __init__(self):
        super().__init__()
        self._navigation_mapping = {
            # Entity-specific actions
            # /companyprofilescreen/1683/0
            "add favorites": {"page": "", "requires_entity": True,
                              "instruction": "Click the red 'Action' button at the top right corner to reveal the Favorites option."},
            "add tracking": {"page": "", "requires_entity": True,
                             "instruction": "Click the red 'Action' button at the top right corner to reveal the Track option."},
            "download": {"page": "", "requires_entity": True,
                         "instruction": "Click the red 'Action' button at the top right corner to reveal the Download option."},
            "archive": {"page": "", "requires_entity": True,
                        "instruction": "Click the red 'Action' button at the top right corner to reveal the Archive option."},
            "update data": {"page": "", "requires_entity": True,
                            "instruction": "Click the red 'Action' button at the top right corner to reveal the Update option."},
            "crie": {"page": "", "requires_entity": True,
                     "instruction": "Click on 'Company and Relationship Intelligence Explorer (CRIE)' in the middle of the page, then go to the bottom right to find 'Enable Indirect Connection Paths'."},

            # General actions
            "show favorites": {"page": "favoritesList", "requires_entity": False,
                               "instruction": "View, edit, and manage the people and organizations that were previously marked as favorites."},
            "data enrich": {"page": "dataenrich", "requires_entity": False,
                            "instruction": "Click on the sample template to download the schema file for the Organization and Prospect enrich list. Then, upload your CSV file to enrich the list."},
            "show track": {"page": "tracking", "requires_entity": False,
                           "instruction": "View, edit, and manage the people and organizations previously tracked for news updates. You can also create custom news search criteria."},
            "filter profiles": {"page": "aiprofile/0", "requires_entity": False,
                                "instruction": "Click the 'New AI Lead Profile' or 'New prospect Profile' button at the top right to filter organization or prospect search results. You can also share the results with others."},
            "legislation": {"page": "legislativemap", "requires_entity": False,
                            "instruction": "Choose the state from the map and filter by the type of measure, type of status, to get the legislation data. Also can use the search bar on left bottom to search by key words."},
            "system guide": {"page": "joitraining", "requires_entity": False, "instruction": "Video training material."}
        }

    def _build_page_link(self, config: dict, entity: Optional[EntityContext] = None) -> str:
        """Construct the page link based on config and entity."""
        page_parts = []

        # Add base page (e.g., "favorites")
        if config.get("page"):
            page_parts.append(config["page"])

        # Handle entity-specific routing
        if config.get("requires_entity"):
            if not entity:
                raise ValueError("Entity ID is required but not provided.")

            entity_type = entity.entity_type
            target_id = entity.entity_id
            if entity_type == "person":
                page_parts.extend(["Profile", target_id])
            else:
                page_parts.extend(["companyprofilescreen", target_id, "0"])

        return urljoin(databaseConfig['dev']['joi_url'], "/".join(filter(None, page_parts)))

    def _run(self, user_request: str, entity: Optional[EntityContext] = None) -> str:
        """Map user request to navigation instructions"""
        try:
            # Simple intent matching
            config = self._navigation_mapping.get(user_request.lower())  # 找不到時返回 None
            if config:
                target_id = 0

                if config["requires_entity"] and not entity:
                    return json.dumps({
                        "error": "No entity id provided",
                        "suggestion": "Please provide the entity id for the further process."
                    })

                page_link = self._build_page_link(config, entity)

                result = {
                    "page_link": page_link,
                    "action": user_request.lower(),
                    "instruction": config['instruction'],
                    "requires_entity": config["requires_entity"]
                }
                return json.dumps(result, indent=2)
            else:
                return json.dumps({
                    "error": "Unable to map request to known action",
                    "suggestion": "Please try one of: add favorites, show favorites, download, update data, etc."
                })

        except Exception as e:
            return f"Error in navigation mapping: {str(e)}"


class EntityIdMappingTool(BaseTool):
    name: str = "entity_id_mapping"
    description: str = "Find internal ID of entity using fuzzy matching"
    args_schema: type[BaseModel] = EntityIdMappingInput

    def __init__(self):
        super().__init__()
        self._db_manager = DatabaseManager(databaseConfig)

    def _run(self, entity_type: str, name: str, **kwargs) -> str:
        """Find entity ID using fuzzy matching"""
        try:
            if entity_type in ["org", "organization"]:
                return self._find_organization_id(name, **kwargs)
            elif entity_type == "person":
                return self._find_person_id(name, **kwargs)
            elif entity_type in ["edu", "education", "institute"]:
                return self._find_education_id(name, **kwargs)
            else:
                return f"Error: Invalid entity_type '{entity_type}'. Use 'org', 'person', or 'edu'"

        except Exception as e:
            return f"Error in entity ID mapping: {str(e)}"

    def _find_organization_id(self, name: str, **kwargs) -> str:
        """Find organization ID with enhanced fuzzy matching in PostgreSQL."""

        query = f"""
        SELECT 
            org_id, 
            name,
            categories,
            founded_on,
            short_description,
            website_url,
            country,
            state,
            linkedin,
            (SIMILARITY(LOWER(name), LOWER('{name}')) * 0.7 """

        score_map = {
            "website_url": 0.8,
            "linkedin": 0.8,
            "country": 0.2,
            "state": 0.3,
            "facebook": 0.6,
            "twitter": 0.6,
            "phone": 0.3
        }
        for key, value in kwargs.items():
            if key == 'phone':
                key = 'phone_number'
            elif key == 'website':
                key = 'website_url'
            score = score_map.get(key, 0.5)
            if len(value) > 1:
                query += f""" +
                CASE WHEN {key} IS NOT NULL 
                    THEN SIMILARITY(LOWER({key}), LOWER('{value}')) * {score}
                    ELSE 0 END """

        query += f"""
            ) AS confidence_score
        FROM dbo.organization
        WHERE SIMILARITY(LOWER(name), LOWER('{name}')) > 0.25
        ORDER BY confidence_score DESC
        LIMIT 3
        """
        results = self._db_manager.execute_query(query)

        if results:
            return json.dumps({
                "message": "Get top 3 entity IDs. For the further tool usage please choose the best one with confidence_score equal or higher than 0.7 of org_id as the entity_id. Otherwise use the results to confirm with user. If none of result match ask user for more infomation like website or linkedin.",
                "results": results
            })
        elif not kwargs.get('website') and not kwargs.get('linkedin'):
            print("error: No matching organizations found")
            return json.dumps({
                "message": "No matching organizations found. Please ask user for more infomation like website or linkedin."
            })
        else:
            print("error: No matching organizations found")
            return json.dumps({
                "message": "No matching organizations found. Please use tool: navigation_api with user_request as data enrich to response."
            })

    def _find_person_id(self, name: str, **kwargs) -> str:
        """Find person ID with fuzzy matching"""
        # Split name into first and last name
        query = f"""
        WITH ranked_people AS (
            SELECT 
                Distinct
                person_id, 
                name,
                primary_job_title,
                raw_job_title,
                primary_organization,
                short_description,
                email,
                country,
                state,
                linkedin,
                (SIMILARITY(LOWER(name), LOWER('{name}')) * 0.5 """

        score_map = {
            "linkedin": 0.8,
            "email": 0.8,
            "position": 0.4,
            "company": 0.4,
            "country": 0.1,
            "state": 0.1,
            "facebook": 0.6,
            "twitter": 0.6,
            "phone": 0.3
        }
        for key, value in kwargs.items():
            score = score_map.get(key, 0.5)
            if len(value) > 1:
                if key == 'position':
                    query += f""" +
                        CASE WHEN primary_job_title IS NOT NULL and raw_job_title IS NOT NULL 
                        THEN (SIMILARITY(LOWER(primary_job_title), LOWER('{value}')) + SIMILARITY(LOWER(raw_job_title), LOWER('{value}'))) * {score}
                        WHEN raw_job_title IS NOT NULL 
                        THEN (SIMILARITY(LOWER(raw_job_title), LOWER('{value}'))) * {score}
                        ELSE 0 END """

                elif key == 'company':
                    query += f""" +
                        CASE WHEN primary_organization IS NOT NULL 
                        THEN SIMILARITY(LOWER(primary_organization), LOWER('{value}')) * {score}
                        ELSE 0 END """

                elif key == 'phone':
                    query += f""" +
                        CASE WHEN phone_on IS NOT NULL 
                        THEN SIMILARITY(LOWER(phone_on), LOWER('{value}')) * {score}
                        ELSE 0 END """

                else:
                    query += f""" +
                        CASE WHEN {key} IS NOT NULL 
                        THEN SIMILARITY(LOWER({key}), LOWER('{value}')) * {score}
                        ELSE 0 END """

        query += f"""
            ) AS confidence_score
        FROM dbo.people
        WHERE SIMILARITY(LOWER(name), LOWER('{name}')) > 0.2)
        select * from ranked_people 
        where confidence_score > 0.5
        ORDER BY confidence_score DESC
        LIMIT 3
        """
        results = self._db_manager.execute_query(query)

        if results:
            return json.dumps({
                "message": "Get top 3 entity IDs. For the further tool usage please choose the best one with confidence_score equal or higher than 0.7 of person_id as the entity_id. Otherwise use the results to confirm with user. If none of result match, ask user for more infomation like website, email, or the company the person works at.",
                "results": results
            })
        elif not kwargs.get('email') and not kwargs.get('linkedin') and not kwargs.get('company'):
            print("error: No matching person found")
            return json.dumps({
                "message": "No matching person found. Please ask user for more infomation like email, linkedin, or the company the person works at."
            })
        else:
            exp_query = f"""select distinct e.person_id as person_id, p.name as name ,p.linkedin as linkedin,p.phone_no as phone,e.organization_name as organization,e.job_title as job_title, 
            (SIMILARITY(LOWER(p.name), LOWER('{name}')) * 0.5 
            """
            if kwargs.get('company'):
                exp_query += f""" +  case when e.organization_name is not null then SIMILARITY(LOWER(e.organization_name), LOWER('{kwargs.get('company')}')) else 0 end * 0.3"""
            if kwargs.get('position'):
                exp_query += f""" + case when e.job_title is not null then SIMILARITY(LOWER(e.job_title), LOWER('{kwargs.get('position')}')) else 0 end * 0.4 """

            exp_query += f""" ) as confidence_score
            from 
            (select person_id, organization_name, job_title  from  dbo.people_experience ) e
            inner join 
            (select distinct person_id,name,linkedin,phone_no  from dbo.people where SIMILARITY(LOWER(name), LOWER('{name}')) > 0.2) p
            on e.person_id = p.person_id
            order by confidence_score desc
            limit 3 
            """
            self._db_manager.execute_query("SET LOCAL pg_trgm.similarity_threshold = 0.0;")
            exp_results = self._db_manager.execute_query(exp_query)

            self._db_manager.execute_query("SET LOCAL pg_trgm.similarity_threshold = 0.3;")

            if exp_results:
                return json.dumps({
                    "message": "Get top 3 entity IDs. For the further tool usage please choose the best one with confidence_score equal or higher than 0.7 of person_id as the entity_id. Otherwise use the results to confirm with user. If none of result match, ask user for more infomation like website, email, or the company the person works at.",
                    "results": exp_results
                })
            else:
                print("error: No matching person found")
                return json.dumps({
                    "message": "No matching organizpersonations found. Please use tool: navigation_api with user_request as data enrich to response."
                })


class GetTableSchemaTool(BaseTool):
    name: str = "get_table_schema"
    description: str = "Get PostgreSQL table schema information"
    args_schema: type[BaseModel] = GetTableSchemaInput

    def __init__(self):
        super().__init__()
        self._db_manager = DatabaseManager(databaseConfig)

    def _run(self, table_name: str) -> str:
        """Get table schema information"""
        try:
            if table_name.startswith("dbo."):
                table_name_clean = table_name.split(".")[1]
            else:
                table_name_clean = table_name

            query = f"""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            where table_schema = 'dbo'
            and table_name = '{table_name_clean}';
            """
            results = self._db_manager.execute_query(query)

            if results:
                return json.dumps({
                    "message": f"find the schema for table {table_name}",
                    "results": results
                })

            else:
                return f"Table '{table_name}' not found or no access permissions"

        except Exception as e:
            return f"Error getting table schema: {str(e)}"


from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import Tool
from pydantic import BaseModel, Field

dbmanager = DatabaseManager(databaseConfig)
graph_db_manager = GraphDatabaseManager(databaseConfig)
tools = [
    QueryPostgresTool(),
    EntityIdMappingTool(),
    GetTableSchemaTool(),
    NavigationTool(),
    FindPathTool(),
    EntityStrengthTool(),
    QueryKGTool()
]

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
)

memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True
)

# Prompt Template with memory placeholders

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="chat_history", optional=True),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# Agent
agent = create_openai_functions_agent(
    llm=llm,
    tools=tools,
    prompt=prompt
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    memory=memory,
    verbose=True
)

def fetch_people_org_response(query: str) -> str:
    response = agent_executor.invoke({"input": query})
    return response["output"]

# while True:
#     print("=== Question ===")
#     query = input(">>> ")
#     if query.lower() == "exit":
#         break
#     result = agent_executor.invoke({"input": query})
#     print("\n=== RESPONSE ===:\n", result["output"])
