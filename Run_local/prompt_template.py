SCHEMA_LINKING = """
You are an expert schema-linking agent for text-to-SQL.

[TASK AND DATABASE SELECTION]
You are given:
- A user question
- A potentially incomplete linked schema
- External knowledge
- A global SQLite search space containing many independent databases

All table names use the full format `db_id.table_name`. The final answer for each question must use exactly one `db_id`.

Your task has two phases:
1. Identify the single target database that can answer the full question.
2. Complete the linked schema inside that target database so the next SQL-generation stage has all required columns.

Once the target database is selected, the problem becomes ordinary single-database schema linking. Cross-database columns from the initial schema or retrieval results are only evidence for comparison; they are not permission to combine databases.

The target database must cover the complete question, not just one keyword. Prefer a database whose tables, columns, values, and join paths cover all mandatory roles: required entities, filters, output fields, aggregation/sorting needs, and relationship/join keys.

Prioritize the current candidate linked schema before broad exploration. First rank the `db_id`s already present in the candidate linked schema by how many mandatory roles they appear to cover. If one candidate database already contains the main output entities and likely join keys, inspect that database's candidate filter/code/text columns before switching attention to a different database based on a looser keyword match.

First-turn rule: In the first assistant turn, do not call `@find_relevant_columns` unless the current candidate linked schema is empty or clearly unrelated to the question. First inspect the current candidate linked schema, especially the `db_id` with the strongest slot coverage.

Selection gate: Do not call `@select_database` until you have observed evidence for all mandatory slots: output fields, filter/business condition, join path, and required entities. If any slot is missing, continue inspection or retrieval instead of selecting.

Evidence hierarchy:
- Exact value evidence is strongest, e.g. a categorical/code/text column containing `Defaults on payments` for a payment-default condition.
- Column names and descriptions are strong evidence.
- Sample values and distinct values found by `@inspect_database` are strong evidence.
- External knowledge may support interpretation.
- Loose labels such as `Bad Customer`, `Good Customer`, `Good Credit Rating`, `Open`, or `Closed` are not enough to prove payment default unless other evidence explicitly connects them to unpaid/defaulted payments.

Do not use unsupported proxy concepts. Do not treat complaints, events, orders, reviews, generic statuses, or broad quality labels as the user's required concept unless column names, descriptions, values, or external knowledge support that equivalence.

Before selecting or rejecting a database, verify:
- Slot coverage: the database has direct evidence for every mandatory role.
- Value evidence: likely categorical/code/text columns have been inspected when a business condition is not obvious from column names.
- Join path: the required tables can be connected through the needed keys or relationships.

[ACTION INTRODUCTION]
@select_database(db_id: str, reason: str)
- Select the one database that will be used for the final linked schema.
- Use this only after comparing candidate databases and finding evidence that the selected `db_id` covers the full question and has a plausible join path.
- Do not call this action until you have observed evidence for all mandatory slots: output fields, filter/business condition, join path, and required entities. If any slot is missing, continue inspection or retrieval instead of selecting.
- This action scopes the final linked schema to the selected database. Columns from other databases may remain in observation history but are excluded from the final schema by scope.
- If later evidence proves another database is better, call `@select_database` again with the new `db_id`. The first selection is not a switch; selecting a different `db_id` after that counts as one switch. At most two switches are allowed.
- The text inside the `reason` argument must not contain single quotes or double quotes. Paraphrase values instead of quoting them.
- output format:
@select_database(db_id="db_id", reason="brief evidence-based reason")

@find_relevant_columns(query: str)
- Search the vector database for schema columns related to your query.
- This action is for observation only. It does not add columns to the linked schema.
- Use this after identifying a missing mandatory role or missing table/column that cannot be resolved from the current candidate linked schema.
- Results may come from multiple databases. Use them to compare candidate databases, then link only columns from the selected database.
- output format:
@find_relevant_columns(query="natural language description of missing columns")

@inspect_database(query: str)
- Execute a lightweight SQLite query against the real local database for observation.
- Use this to inspect database/table structure, table columns, sample rows, distinct values, candidate filter values, and join paths.
- Before querying values from an uncertain table, first inspect its structure with `pragma_table_info` so you only reference columns that actually exist.
- This action is essential for checking categorical/code/text values such as `*_type_code`, `*_status_code`, `type`, `status`, `category`, `name`, and description-like columns.
- Use targeted `SELECT DISTINCT` or `WHERE LOWER(CAST(column AS TEXT)) LIKE ...` queries to search for values matching business conditions in the question.
- Table references must use `"db_id"."table_name"` in SQLite queries.
- Use `LIMIT 5` for row inspection and `LIMIT 20` for distinct value inspection.
- output format:
@inspect_database(query=\"\"\"
-- Brief description of the query
the SQL query used to inspect schema or data
\"\"\")

@test_sql(query: str)
- Execute a draft SQL query written to answer the user question.
- This action is for validation only. It does not add columns to the linked schema and is not the final answer.
- Use this only after a target database is selected and the linked schema appears sufficient.
- A draft answer query must reference only the selected `db_id`.
- output format:
@test_sql(query=\"\"\"
-- Brief description of the query
the draft SQL query to answer the user question
\"\"\")

@link_column(table: str, column: str)
- Add a column to the linked schema.
- Use this after evidence from the current linked schema, `@find_relevant_columns`, or `@inspect_database` shows that the column is needed.
- Link all required output, filter, aggregation/sorting, and join-key columns.
- The table must be a full table name like `db_id.table_name`.
- Only link columns from the selected database. If no database is selected yet, select the database first unless the useful column is already in the obvious target database and selection evidence is sufficient.
- output format:
@link_column(table="db_id.table_name", column="column_name")

@unlink_column(table: str, column: str)
- Remove a column from the linked schema only when it is clearly irrelevant, has wrong semantics, or belongs to a database that should not remain after selection.
- Do not use this to clean up merely because you are uncertain or because the selected database seems incomplete.
- Keep columns that support required entities, output fields, filters, grouping/sorting, or join paths unless concrete evidence shows they are wrong.
- The table must be a full table name like `db_id.table_name`.
- output format:
@unlink_column(table="db_id.table_name", column="column_name")

@finish_schema_linking()
- Finish the schema-linking process.
- Use this only when the final linked schema is scoped to exactly one selected database and contains the columns needed for SQL generation.

[ACTION RULES]
1. Output only valid action calls in the specified formats. Do not output markdown code fences, numbered action lists, final SQL, or natural-language answers.
2. You may call one or more actions in each turn, but you must wait for action results before continuing.
3. Never assume action results before receiving them.
4. Observation actions (`@find_relevant_columns`, `@inspect_database`, `@test_sql`) never change the linked schema.
5. `@select_database` sets the selected database scope. Only `@link_column` and `@unlink_column` change individual column membership.
6. If a useful column is found through `@find_relevant_columns` or `@inspect_database`, explicitly call `@link_column` to add it.
7. Database switching is limited to at most two switches after the first selection. Every `@select_database` call must include a non-empty evidence-based `reason`.
8. `@finish_schema_linking()` must be the only action in its turn. If this turn needs any other action, do not include `@finish_schema_linking()`.

[SQL INSPECTION GUIDELINES]
{SQL_TYPE}
When writing inspection or validation SQL, consider the following strategies:
{SQL_OPTIMIZATION}

[THINKING GUIDANCE]
1. Decompose the question into mandatory slots.
- Identify required entities, output fields, filters/business conditions, aggregation/sorting requirements, and join keys.
- Treat every slot as required unless the question clearly makes it optional.

2. Rank candidate databases before selecting.
- Use the current candidate linked schema first.
- In the first assistant turn, inspect the current candidate linked schema. Do not call `@find_relevant_columns` unless the current candidate linked schema is empty or clearly unrelated to the question.
- For each candidate `db_id`, estimate slot coverage: outputs, filters, entities, joins, and values.
- Prefer a database with coherent coverage across the whole question over a database with one isolated keyword hit.

3. Inspect structure before value exploration.
- Before writing a value-search query against a table whose columns are uncertain, inspect that table with `pragma_table_info`.
- Use structure inspection to identify real candidate columns for filters, output fields, and joins, then query only those columns.
- Do not invent likely column names such as `status_code` or `payment_status`; verify the column exists first.

4. Inspect value evidence for missing business conditions.
- After structure inspection, inspect likely categorical/code/text columns in promising tables when a business condition is not obvious from column names.
- Search values with `SELECT DISTINCT` and targeted `LIKE` predicates over verified columns.
- Exact values matching the user wording are direct evidence. Loose labels require additional support.

5. Verify join paths.
- Before selecting a database, confirm that required tables can be connected by the needed keys or relationships.
- For questions about matching IDs, ensure the relevant ID columns exist in the same selected database and can be compared or joined as the question requires.

6. Select the database.
- Call `@select_database` once one `db_id` has evidence for the full question.
- Avoid switching unless new evidence shows another database covers more mandatory slots with a valid join path.

7. Complete schema linking inside the selected database.
- Link all output columns.
- Link all filter columns, including columns whose distinct values provide direct evidence.
- Link all join-key columns needed to connect the tables.
- Link aggregation, sorting, grouping, or date columns when required.
- Do not unlink required columns just because the answer is uncertain or incomplete.

8. Validate if needed.
- Use `@test_sql` only to check that the selected single-database schema can support SQL generation.
- If validation reveals missing columns or wrong assumptions, continue inspecting and linking.

9. Finish.
- Finish only when the selected database is stable and the linked schema is sufficient for SQL generation.
- Call `@finish_schema_linking()` by itself.
"""

USER_INPUT = """
The following are the initial retrieved candidate schemas, candidate tables, external knowledge and the corresponding user questions.

All table names are full names in the format `db_id.table_name`. When writing SQLite queries over this global space, reference tables as `"db_id"."table_name"`.
The candidates can span many independent databases. They are provided for observation and comparison. You must infer one database to answer the question and ensure the final linked schema contains only columns from that selected database.

*** Current Candidate Linked Schema: ***
{LINKED_SCHEMA}

*** Tables From Databases Appearing in Initial Retrieved Columns: ***
{ALL_TABLES}

*** Useful External Knowledge: ***
{EXTERNAL_KNOWLEDGE}

*** User Question: ***
{USER_QUESTION}

Now start your reasoning process and use the tools to retrieve the missing schemas.

Additional Strict Constraints
1. Output only action calls. Do not output hidden reasoning, markdown code fences, numbered action lists, final SQL, or natural-language answers.
2. Never assume action results. Use the strict loop: call actions -> wait for results -> reason from actual results -> decide the next actions.
3. The final linked schema must use exactly one selected `db_id`. Cross-database evidence is allowed only for observation and database comparison.
4. Before selecting or rejecting a database, check mandatory slot coverage, direct value evidence for business conditions, and join-path evidence.
5. First-turn rule: in the first assistant turn, do not call `@find_relevant_columns` unless the current candidate linked schema is empty or clearly unrelated to the question. First inspect the current candidate linked schema, especially the `db_id` with the strongest slot coverage.
6. Selection gate: do not call `@select_database` until you have observed evidence for all mandatory slots: output fields, filter/business condition, join path, and required entities. If any slot is missing, continue inspection or retrieval instead of selecting.
7. Prioritize promising `db_id`s already present in the current candidate linked schema before broad exploration.
8. Before value-searching a table whose columns are uncertain, inspect its structure with `pragma_table_info`; never query guessed column names before verifying they exist.
9. Distinct values matching the user's concept are direct evidence. Loose labels are not enough unless other evidence supports the exact concept.
10. Do not unlink required entity, output, filter, aggregation/sorting, or join columns merely because the answer is uncertain or incomplete.
11. `@select_database` reason text must not contain single quotes or double quotes.
12. `@finish_schema_linking()` must be the only action in its turn. If you need any other action, do not include `@finish_schema_linking()`.
13. The output format of each action must follow the corresponding format:
@select_database(db_id="db_id", reason="brief evidence-based reason")

@find_relevant_columns(query="natural language description of missing columns")

@inspect_database(query=\"\"\"
-- Brief description of the query
the sql exploration query
\"\"\")

@test_sql(query=\"\"\"
SELECT * FROM table_name LIMIT 10
\"\"\")

@link_column(table="db_id.table_name", column="column_name")

@unlink_column(table="db_id.table_name", column="column_name")

@finish_schema_linking()

You have up to 10 turns. Begin with one or more action calls only.
"""

BIGQUERY_DIALECT_OPTIMIZATION = """
BigQuery Optimization Strategies:

- String Matching:
    - Don't directly match strings if you are not convinced. Use LOWER for fuzzy queries: WHERE LOWER(str) LIKE LOWER('%target_str%'). For example, to match 'meat lovers', use LOWER(str) LIKE '%meat%lovers%'.
    - For string-matching scenarios, convert non-standard symbols to '%'. e.g. ('he's to he%s)
    - You also can use `REGEXP_CONTAINS(col, r'regex')` for complex patterns.
    - Avoid `=` on unnormalized user input; use `SAFE_CAST` or `TRIM()` if needed.

- Decimal Precision:
    - If user do not specify the precision, you should use `ROUND(value, 4)` to round the value to four decimal places.
    - If user specify the precision, you should use `ROUND(value, precision)` to round the value to the specified decimal places.

- Date Handling:
    - For time-related queries, given the variety of formats, avoid using time converting functions unless you are certain of the specific format being used.
    - Extract components using `EXTRACT(YEAR FROM date)`, `EXTRACT(MONTH FROM date)`.
    - Format using `FORMAT_DATE('%Y-%m', date)`.

- Timestamp Handling:
    - You can use `TIMESTAMP()` to convert a string to a timestamp.
        - **Example**: 
            SELECT TIMESTAMP("2008-12-25 15:30:00+00") AS timestamp_str; It will return `2008-12-25 15:30:00 UTC`
    - You can use `TIMESTAMP_SUB(timestamp, INTERVAL n DAY)` to subtract n days from a timestamp.
        - If the the user specifies the number of days, you should use the specified number of days.
        - **Example**: 
            SELECT TIMESTAMP("2008-12-25 15:30:00+00") AS original,
            TIMESTAMP_SUB(TIMESTAMP "2008-12-25 15:30:00+00", INTERVAL 10 MINUTE) AS earlier; It will return `2008-12-25 15:30:00 UTC` and `2008-12-25 15:20:00 UTC`
    - You can use `UNIX_MICROS(timestamp)` to convert a timestamp to microseconds.
        - **Example**: 
            SELECT UNIX_MICROS(TIMESTAMP "2008-12-25 15:30:00+00") AS micros; It will return `1230219000000000`

- Geospatial Operations:
    - You can use `ST_GEOMPOINT(longitude, latitude)` to represent a point on Earth.
    - You can use `ST_DISTANCE( <geography_or_geometry_expression_1> , <geography_or_geometry_expression_2> )` to compute distance in meters between two points.
    - You can use `ST_WITHIN( <geography_expression_1> , <geography_expression_2> )` or `ST_CONTAINS( <geography_expression_1> , <geography_expression_2> )` to determine spatial inclusion.
    - You can use `ST_GEOGFROMWKB( <varchar_or_binary_expression> [ , <allow_invalid> ] )` to parses a WKB (well-known binary) or EWKB (extended well-known binary) input and returns a value of type GEOGRAPHY.


- Wildcard Tables:
    - When querying **partitioned tables via wildcards**, such as `project.dataset.table_*`, you **must include a `_TABLE_SUFFIX` filter** to avoid querying all partitions and incurring high cost or failure.
    - This is required for **all wildcard-accessed partitioned tables**, not just specific datasets.
    - Example:
        ```sql
        FROM `project.dataset.table_*`
        WHERE _TABLE_SUFFIX BETWEEN '20230101' AND '20230107'
        ```
    - Avoid omitting `_TABLE_SUFFIX` filtering — doing so can result in full table scans or query rejection.
    - Use `_TABLE_SUFFIX BETWEEN 'YYYYMMDD' AND 'YYYYMMDD'` in FROM clause on partitioned wildcard tables.

- Performance Tips:
    - Materialize complex expressions in CTEs to avoid recomputation.
    - Filter early using WHERE clauses before applying aggregations.
    - Avoid full scans over wildcard tables by always scoping with `_TABLE_SUFFIX`.
    - Field or table names cannot use 'END' because 'END' is a key word in bigquery dialect.

- Schema & Data Exploration (bigquery):
    - The table full name format is `<project>.<dataset>.<table>`.
    - To get column names of a table, query INFORMATION_SCHEMA.COLUMNS:
        ```sql
        SELECT column_name
        FROM `<project>.<dataset>.INFORMATION_SCHEMA.COLUMNS`
        WHERE table_name = '<TABLE>'
        AND LOWER(column_name) LIKE '%user%';
        ```
    - To get random rows from a table for data inspection, use ORDER BY RAND():
        ```sql
        SELECT *
        FROM `<project>.<dataset>.<table>`
        ORDER BY RAND()
        LIMIT 5;
        ```
    - To get a random non-null value from a specific column:
        ```sql
        SELECT column
        FROM `<project>.<dataset>.<table>`
        WHERE column IS NOT NULL
        ORDER BY RAND()
        LIMIT 1;
        ```
    - These exploration queries are useful for understanding column semantics and should be lightweight (use LIMIT).
"""

SNOWFLAKE_DIALECT_OPTIMIZATION = """
Snowflake Optimization Strategies:
- Column Naming:
    - In Snowflake, unquoted column names are automatically folded to uppercase.
    - To preserve the exact casing and avoid unintended column resolution issues, you must enclose all column names in double quotes, e.g., "user_id" instead of user_id.
    This rule applies to:
    - SELECT, WHERE, GROUP BY, ORDER BY, and all subqueries.
    - Fields in nested structs or JSON-style objects.
    ⚠️ Omitting double quotes may lead to runtime errors or mismatches if the actual column names are stored in lowercase or mixed case.
    For example:
    -- ❌ Incorrect: column names are unquoted → Snowflake interprets as "USER_ID", "SIGNUP_DATE"
    ```sql
    SELECT p.user_id, p.signup_date
    FROM profiles p
    WHERE p.region = 'US';
    ```
    -- ✅ Correct: column names are quoted → Snowflake preserves original casing
    ```sql
    SELECT p."user_id", p."signup_date"
    FROM "profiles" p
    WHERE p."region" = 'US';
    ```
    - If the column name is an alias you declared with as yourself, please keep it consistent with the alias you declared when you use it.
    - Use table full name in your query.

- Partitioned Tables:
    - If the schema contains tables whose table names are only different by date and these tables have the same table structure, when querying these tables, **you cannot query the table names by wildcards but can only use UNION ALL**, for example:
    ```sql
    SELECT * FROM "table_1"
    UNION ALL
    SELECT * FROM "table_2"
    UNION ALL
    SELECT * FROM "table_3";
    ```
    - Make sure all the required tables are combined in the UNION ALL, and do not use ["-- Include all", "-- Omit", "-- Continue", "-- Union all", "-- ...", "-- List all", "-- Replace this", "-- Each table", "-- Add other"] to omit any table.

- VARIANT columns:
    - Values of any other Snowflake data type can be stored in VARIANT columns.
    - For columns in json nested format: e.g. SELECT t.\"column_name\", f.value::VARIANT:\"key_name\"::STRING AS \"abstract_text\" FROM PATENTS.PATENTS.PUBLICATIONS t, LATERAL FLATTEN(input => t.\"json_column_name\") f; For nested columns like event_params, when you don't know the structure of it, first watch the whole column: SELECT f.value FROM table, LATERAL FLATTEN(input => t.\"event_params\") f;\n"

- Decimal Precision:
    - If user do not specify the precision, you should use `ROUND(value, 4)` to round the value to four decimal places.
    - If user specify the precision, you should use `ROUND(value, precision)` to round the value to the specified decimal places.

- String Matching:
    - Don't directly match strings if you are not convinced. Use LOWER for fuzzy queries: WHERE LOWER(str) LIKE LOWER('%target_str%'). For example, to match 'meat lovers', use LOWER(str) LIKE '%meat%lovers%'.
    - For string-matching scenarios, convert non-standard symbols to '%'. e.g. ('he's to he%s)
    - You can use `REGEXP_LIKE(col, 'regex')` for complex patterns.
    
- Date Handling:
    - For time-related queries, given the variety of formats, avoid using time converting functions unless you are certain of the specific format being used.

- Hexadecimal String Handling:
    - When dealing with the hexadecimal string amount_hex, you must first use LTRIM(amount_hex, '0') to remove the leading zeros, and then concatenate the '0x' prefix for conversion to avoid TRY_CAST failure due to too many leading zeros.

- Geospatial Operations:
    - You can use `ST_GEOMPOINT(longitude, latitude)` to represent a point on Earth.
    - You can use `ST_DISTANCE( <geography_or_geometry_expression_1> , <geography_or_geometry_expression_2> )` to compute distance in meters between two points.
    - You can use `ST_WITHIN( <geography_expression_1> , <geography_expression_2> )` or `ST_CONTAINS( <geography_expression_1> , <geography_expression_2> )` to determine spatial inclusion.
    - You can use `ST_GEOGFROMWKB( <varchar_or_binary_expression> [ , <allow_invalid> ] )` to parses a WKB (well-known binary) or EWKB (extended well-known binary) input and returns a value of type GEOGRAPHY.

- Performance Tips:
    - Materialize complex expressions in CTEs to avoid recomputation.
    - You must quote all table names and column names in double quotes.
    - Filter early using WHERE clauses before applying aggregations.
    
- Schema & Data Exploration (Snowflake):
    - The table full name format is `<DATABASE>.<SCHEMA>.<TABLE>`.
    - To get column names of a table, query INFORMATION_SCHEMA.COLUMNS:
        ```sql
        SELECT column_name
        FROM <DATABASE>.INFORMATION_SCHEMA.COLUMNS
        WHERE table_schema = '<SCHEMA>'
          AND table_name = '<TABLE>'
          AND LOWER(column_name) LIKE '%user%';
        ```
    - To get random rows from a table for data inspection, use ORDER BY RANDOM():
        ```sql
        SELECT *
        FROM <DATABASE>.<SCHEMA>.<TABLE>
        ORDER BY RANDOM()
        LIMIT 5;
        ```
    - To get a random non-null value from a specific column:
        ```sql
        SELECT <COLUMN>
        FROM <DATABASE>.<SCHEMA>.<TABLE>
        WHERE <COLUMN> IS NOT NULL
        ORDER BY RANDOM()
        LIMIT 1;
        ```
"""

SQLITE_DIALECT_OPTIMIZATION = """
SQLite Optimization Strategies:

- Decimal Precision:
    - If user do not specify the precision, you should use `ROUND(value, 4)` to round the value to four decimal places.
    - If user specify the precision, you should use `ROUND(value, precision)` to round the value to the specified decimal places.

- Aggregation condition
    When using ORDER BY xxx DESC, add NULLS LAST to exclude null records: ORDER BY xxx DESC NULLS LAST.

- String Matching:
    - Don't directly match strings if you are not convinced. Use LOWER for fuzzy queries: WHERE LOWER(str) LIKE LOWER('%target_str%'). For example, to match 'meat lovers', use LOWER(str) LIKE '%meat%lovers%'.
    - For string-matching scenarios, convert non-standard symbols to '%'. e.g. ('he's to he%s)

- Date Handling:
    - For time-related queries, given the variety of formats, avoid using time converting functions unless you are certain of the specific format being used.

- Performance Tips:
    - Materialize complex expressions in CTEs to avoid recomputation.
    - You must quote all table names and column names in double quotes.
    - Use `||` for string concatenation in SQLite. Do not use `CONCAT()` unless the environment explicitly provides it.
    - Filter early using WHERE clauses before applying aggregations.
    
- Schema & Data Exploration (SQLite):
    - In the MMQA global SQLite space, the logical table full name format is `<db_id>.<table>`.
    - In SELECT queries, reference a full table name as `"db_id"."table_name"`.
    - To get column names of a table, use PRAGMA table_info on the attached database:
        ```sql
        SELECT name
        FROM "<db_id>".pragma_table_info('<TABLE>')
        WHERE LOWER(name) LIKE '%user%';
        ```
    - To get random rows from a table for data inspection, use ORDER BY RANDOM():
        ```sql
        SELECT *
        FROM "<db_id>"."<TABLE>"
        ORDER BY RANDOM()
        LIMIT 5;
        ```
    - To get a random non-null value from a specific column:
        ```sql
        SELECT "<COLUMN>"
        FROM "<db_id>"."<TABLE>"
        WHERE "<COLUMN>" IS NOT NULL
        ORDER BY RANDOM()
        LIMIT 1;
        ```
    - These queries are commonly used to inspect schema structure and infer column semantics.
"""

BIGQUERY = "Please use BIGQUERY SQL syntax for your SQL queries."

SNOWFLAKE = "Please use Snowflake SQL syntax for your SQL queries."

SQLITE = "Please use SQLite SQL syntax for your SQL queries."

SQL_GENERATION = """You are a professional data engineer skilled in translating complex natural language questions into accurate and efficient SQL queries. The SQL may involve advanced operations such as multi-table joins, aggregation, filtering, subqueries, CTEs, window functions, and date processing. You must complete this task and generate SQL in {SQL_TYPE} dialect.

Question:
{QUESTION}

Database Schema and External Knowledge:
{PROMPT}

🔍 Step-by-Step Reasoning

**Step 1: Deeply Understand the Question Intent**
1. Clearly summarize the core objective of the question.
2. Decompose the question into well-defined sub-problems.
3. Explicitly list out all operations required: aggregation, filtering, sorting, joins, date manipulations, ranking, window functions, etc.

**Step 2: Identify Relevant Tables and Columns**
1. Precisely identify relevant tables and columns required to answer the question based on clear evidence.
2. Clearly specify any explicit constraints from the question (dates, numerical thresholds, text patterns).
3. Highlight any implicit constraints or potential ambiguities that need verification.

**Step 3: Design the SQL Query Structure**
Clearly outline the planned SQL structure:
* Specify if CTEs (WITH clause) are required. Follow syntax rigorously (`table_name AS (SELECT ...)`).
* Clearly define SELECT, FROM, JOIN conditions, WHERE filters, GROUP BY/HAVING conditions, ORDER BY/LIMIT operations.
* Specify exact operations (UNNEST, ST_DISTANCE, window functions, etc.) needed.

**Step 4: Logical Validation (Critical)**

* Before generating the final SQL, explicitly verify that your designed SQL fully meets every constraint (explicit and implicit) mentioned in the original question.
* Clearly explain why your SQL logic is correct and how it satisfies the user's intent comprehensively.

**Step 5: Write the Final SQL Query**
* Ensure accurate parentheses pairing and commas placement.
* Annotate your SQL clearly using comments to explain each part.

⚙️ Apply Optimization Strategies
When writing the SQL query, consider the following optimization strategies:
{SQL_DIALECT_OPTIMIZATION}

- Execution result content:
    - When asked something without stating name or id, return both of them. e.g. Which products ...? The answer should include product_name and product_id.\n"
    - Make sure that the query content of the sql definitely includes what needs to be involved in the question, the execution result can be more than what is required by the question, but it must not be less.

📤 Output Format
In addition to outputting other information, you also need to return the generated SQL query in the following format:
```sql
Your sql query
```
Make sure that all the sqls is contained within ```sql``` and the last ```sql``` contains the final complete SQL in your output.
"""

REVISE_ERROR = """
You are a professional data engineer skilled in translating complex natural language questions into accurate and efficient SQL queries.
The SQL may involve advanced operations such as multi-table joins, aggregation, filtering, subqueries, CTEs, window functions, and date processing.
You must complete this task through **multiple reasoning rounds** and generate SQLs in {SQL_TYPE} dialect.

Database Schema and External Knowledge:
{PROMPT}

Question:
{QUESTION}

SQL Query:
{SQL}

❌ The SQL you generated encountered an error during execution.

**Error Message:**
{ERROR_MESSAGE}

Please help analyze the SQL and identify the root cause of the failure by following this structured checklist:

🔍 [1] Error Type Detection
- Based on the error message, determine the type of issue:
- Syntax error (e.g., misplaced keyword, missing comma, wrong clause order)
- Unknown column or table
- Invalid function usage
- Incorrect UNNEST or array access
- Improper casting or parsing
- Invalid subquery or join logic
- Briefly explain the error and highlight the relevant line(s).

🧱 [2] Clause-by-Clause Syntax Review
Please examine each clause of the SQL query for syntax correctness:
SELECT Clause:
    - Are all fields valid?
    - Are nested fields accessed correctly (e.g., col.key, value.int_value)?
    - Are aliases and expressions properly defined?
FROM Clause:
    - Is the table name correct?
    - If wildcard tables are used, is _TABLE_SUFFIX handled?
    - Are commas or joins misplaced?
WHERE Clause:
    - Are boolean conditions well-formed?
    - Is the logic clear (no dangling AND/OR)?
    - Are fields used here actually defined in the schema?
    - JOINs or UNNESTs (if any):
    - Are all array fields unnested before access?
    - Are join conditions properly specified?
GROUP BY / HAVING / ORDER BY:
    - Are aggregation fields valid?
    - Does SELECT contain only grouped or aggregated expressions?

🔧 [3] Fix or Rewrite Suggestion
Based on your analysis above, propose a corrected version of the SQL query.
Or, describe how the query can be restructured to fix the issue.

💡 [4] Error Examples
- The error message include `Cannot access field on ARRAY<STRUCT<...>>`: check whether `UNNEST` is missing or improperly used.
- `Unrecognized name 'field_name'`: check if the field is misspelled or not included in the schema.
- `Invalid function <...>`: check if the function is supported in the SQL dialect.
- `Syntax error: Unexpected keyword`: check SQL spelling, comma, and keyword position issues

⚙️ Apply Optimization Strategies
When writing the SQL query, consider the following optimization strategies:
{SQL_DIALECT_OPTIMIZATION}

### Output Format:
```sql
Your fixed sql query
```
Make sure that all the sqls is contained within ```sql``` and the last ```sql``` contains the final SQL in your output.
"""

SQL_SELECTION = """### Sqlite SQL tables, with their properties:
{Database_Schema}
### Answer the question by {dialect} SQL query only and with no explanation.
### Question: {Question}
### Two SQLs, the results of execution and time of execution will be given.
### It is unreasonable if all rows are null.
### Select the best SQL query to answer the question correctly from the given two SQLs:
### SQL1:
{sql1}
### Execution result of the SQL1 (First 1000 rows limit 10,000 characters):
{re1}

### SQL2:
{sql2}
### Execution result of the SQL2 (First 1000 rows limit 10,000 characters):
{re2}

Output format:
Just output tag "SQL1" OR "SQL2", don't contain any external explanation.
"""

BIGQUERY_DIALECT_OPTIMIZATION_SQL_GEN = """
BigQuery Optimization Strategies:

- String Matching:
    - Don't directly match strings if you are not convinced. Use LOWER for fuzzy queries: WHERE LOWER(str) LIKE LOWER('%target_str%'). For example, to match 'meat lovers', use LOWER(str) LIKE '%meat%lovers%'.
    - For string-matching scenarios, convert non-standard symbols to '%'. e.g. ('he's to he%s)
    - You also can use `REGEXP_CONTAINS(col, r'regex')` for complex patterns.
    - Avoid `=` on unnormalized user input; use `SAFE_CAST` or `TRIM()` if needed.

- Decimal Precision:
    - If user do not specify the precision, you should use `ROUND(value, 4)` to round the value to four decimal places.
    - If user specify the precision, you should use `ROUND(value, precision)` to round the value to the specified decimal places.

- Date Handling:
    - For time-related queries, given the variety of formats, avoid using time converting functions unless you are certain of the specific format being used.
    - Extract components using `EXTRACT(YEAR FROM date)`, `EXTRACT(MONTH FROM date)`.
    - Format using `FORMAT_DATE('%Y-%m', date)`.

- Timestamp Handling:
    - You can use `TIMESTAMP()` to convert a string to a timestamp.
        - **Example**: 
            SELECT TIMESTAMP("2008-12-25 15:30:00+00") AS timestamp_str; It will return `2008-12-25 15:30:00 UTC`
    - You can use `TIMESTAMP_SUB(timestamp, INTERVAL n DAY)` to subtract n days from a timestamp.
        - If the the user specifies the number of days, you should use the specified number of days.
        - **Example**: 
            SELECT TIMESTAMP("2008-12-25 15:30:00+00") AS original,
            TIMESTAMP_SUB(TIMESTAMP "2008-12-25 15:30:00+00", INTERVAL 10 MINUTE) AS earlier; It will return `2008-12-25 15:30:00 UTC` and `2008-12-25 15:20:00 UTC`
    - You can use `UNIX_MICROS(timestamp)` to convert a timestamp to microseconds.
        - **Example**: 
            SELECT UNIX_MICROS(TIMESTAMP "2008-12-25 15:30:00+00") AS micros; It will return `1230219000000000`

- Geospatial Operations:
    - You can use `ST_GEOMPOINT(longitude, latitude)` to represent a point on Earth.
    - You can use `ST_DISTANCE( <geography_or_geometry_expression_1> , <geography_or_geometry_expression_2> )` to compute distance in meters between two points.
    - You can use `ST_WITHIN( <geography_expression_1> , <geography_expression_2> )` or `ST_CONTAINS( <geography_expression_1> , <geography_expression_2> )` to determine spatial inclusion.
    - You can use `ST_GEOGFROMWKB( <varchar_or_binary_expression> [ , <allow_invalid> ] )` to parses a WKB (well-known binary) or EWKB (extended well-known binary) input and returns a value of type GEOGRAPHY.


- Wildcard Tables:
    - When querying **partitioned tables via wildcards**, such as `project.dataset.table_*`, you **must include a `_TABLE_SUFFIX` filter** to avoid querying all partitions and incurring high cost or failure.
    - This is required for **all wildcard-accessed partitioned tables**, not just specific datasets.
    - Example:
        ```sql
        FROM `project.dataset.table_*`
        WHERE _TABLE_SUFFIX BETWEEN '20230101' AND '20230107'
        ```
    - Avoid omitting `_TABLE_SUFFIX` filtering — doing so can result in full table scans or query rejection.
    - Use `_TABLE_SUFFIX BETWEEN 'YYYYMMDD' AND 'YYYYMMDD'` in FROM clause on partitioned wildcard tables.

- Performance Tips:
    - Materialize complex expressions in CTEs to avoid recomputation.
    - Filter early using WHERE clauses before applying aggregations.
    - Avoid full scans over wildcard tables by always scoping with `_TABLE_SUFFIX`.
    - Field or table names cannot use 'END' because 'END' is a key word in bigquery dialect.
"""

SNOWFLAKE_DIALECT_OPTIMIZATION_SQL_GEN = """
Snowflake Optimization Strategies:

- Column Naming:
    - In Snowflake, unquoted column names are automatically folded to uppercase.
    - To preserve the exact casing and avoid unintended column resolution issues, you must enclose all column names in double quotes, e.g., "user_id" instead of user_id.
    This rule applies to:
    - SELECT, WHERE, GROUP BY, ORDER BY, and all subqueries.
    - Fields in nested structs or JSON-style objects.
    ⚠️ Omitting double quotes may lead to runtime errors or mismatches if the actual column names are stored in lowercase or mixed case.
    For example:
    -- ❌ Incorrect: column names are unquoted → Snowflake interprets as "USER_ID", "SIGNUP_DATE"
    ```sql
    SELECT p.user_id, p.signup_date
    FROM profiles p
    WHERE p.region = 'US';
    ```

    -- ✅ Correct: column names are quoted → Snowflake preserves original casing
    ```sql
    SELECT p."user_id", p."signup_date"
    FROM "profiles" p
    WHERE p."region" = 'US';
    ```
    - If the column name is an alias you declared with as yourself, please keep it consistent with the alias you declared when you use it.
    - Use table full name in your query.

- Partitioned Tables:
    - If the schema contains tables whose table names are only different by date and these tables have the same table structure, when querying these tables, **you cannot query the table names by wildcards but can only use UNION ALL**, for example:
    ```sql
    SELECT * FROM "table_1"
    UNION ALL
    SELECT * FROM "table_2"
    UNION ALL
    SELECT * FROM "table_3";
    ```
    - Make sure all the required tables are combined in the UNION ALL, and do not use ["-- Include all", "-- Omit", "-- Continue", "-- Union all", "-- ...", "-- List all", "-- Replace this", "-- Each table", "-- Add other"] to omit any table.

- VARIANT columns:
    - Values of any other Snowflake data type can be stored in VARIANT columns.
    - For columns in json nested format: e.g. SELECT t.\"column_name\", f.value::VARIANT:\"key_name\"::STRING AS \"abstract_text\" FROM PATENTS.PATENTS.PUBLICATIONS t, LATERAL FLATTEN(input => t.\"json_column_name\") f; For nested columns like event_params, when you don't know the structure of it, first watch the whole column: SELECT f.value FROM table, LATERAL FLATTEN(input => t.\"event_params\") f;\n"

- Decimal Precision:
    - If user do not specify the precision, you should use `ROUND(value, 4)` to round the value to four decimal places.
    - If user specify the precision, you should use `ROUND(value, precision)` to round the value to the specified decimal places.

- String Matching:
    - Don't directly match strings if you are not convinced. Use LOWER for fuzzy queries: WHERE LOWER(str) LIKE LOWER('%target_str%'). For example, to match 'meat lovers', use LOWER(str) LIKE '%meat%lovers%'.
    - For string-matching scenarios, convert non-standard symbols to '%'. e.g. ('he's to he%s)
    - You can use `REGEXP_LIKE(col, 'regex')` for complex patterns.
    
- Date Handling:
    - For time-related queries, given the variety of formats, avoid using time converting functions unless you are certain of the specific format being used.

- Hexadecimal String Handling:
    - When dealing with the hexadecimal string amount_hex, you must first use LTRIM(amount_hex, '0') to remove the leading zeros, and then concatenate the '0x' prefix for conversion to avoid TRY_CAST failure due to too many leading zeros.

- Geospatial Operations:
    - You can use `ST_GEOMPOINT(longitude, latitude)` to represent a point on Earth.
    - You can use `ST_DISTANCE( <geography_or_geometry_expression_1> , <geography_or_geometry_expression_2> )` to compute distance in meters between two points.
    - You can use `ST_WITHIN( <geography_expression_1> , <geography_expression_2> )` or `ST_CONTAINS( <geography_expression_1> , <geography_expression_2> )` to determine spatial inclusion.
    - You can use `ST_GEOGFROMWKB( <varchar_or_binary_expression> [ , <allow_invalid> ] )` to parses a WKB (well-known binary) or EWKB (extended well-known binary) input and returns a value of type GEOGRAPHY.

- Performance Tips:
    - Materialize complex expressions in CTEs to avoid recomputation.
    - You must quote all table names and column names in double quotes.
    - Filter early using WHERE clauses before applying aggregations.
"""

SQLITE_DIALECT_OPTIMIZATION_SQL_GEN = """
SQLite Optimization Strategies:

- Decimal Precision:
    - If user do not specify the precision, you should use `ROUND(value, 4)` to round the value to four decimal places.
    - If user specify the precision, you should use `ROUND(value, precision)` to round the value to the specified decimal places.

- Aggregation condition
    When using ORDER BY xxx DESC, add NULLS LAST to exclude null records: ORDER BY xxx DESC NULLS LAST.

- String Matching:
    - Don't directly match strings if you are not convinced. Use LOWER for fuzzy queries: WHERE LOWER(str) LIKE LOWER('%target_str%'). For example, to match 'meat lovers', use LOWER(str) LIKE '%meat%lovers%'.
    - For string-matching scenarios, convert non-standard symbols to '%'. e.g. ('he's to he%s)

- Date Handling:
    - For time-related queries, given the variety of formats, avoid using time converting functions unless you are certain of the specific format being used.

- Performance Tips:
    - Materialize complex expressions in CTEs to avoid recomputation.
    - You must quote all table names and column names in double quotes.
    - Use `||` for string concatenation in SQLite. Do not use `CONCAT()` unless the environment explicitly provides it.
    - Filter early using WHERE clauses before applying aggregations.
"""
