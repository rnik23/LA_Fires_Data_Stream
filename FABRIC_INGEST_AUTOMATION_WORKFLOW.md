# Microsoft Fabric Ingest Automation Workflow

## Objective
Automate the current manual process of reading complex production SQL, isolating source tables from CTE-heavy queries, and provisioning or updating ingestion pipelines for each distinct source table used by the business.

The design below assumes Microsoft Fabric as the operating platform and uses:
- **Fabric Pipelines** for orchestration and operational scheduling.
- **Fabric Notebooks** for SQL parsing, metadata extraction, rule evaluation, and code generation.
- **Lakehouse / Warehouse tables** for metadata, control, audit, and orchestration state.
- **Optional Fabric Dataflow Gen2 / Copy activity** for source-specific ingest patterns.
- **Optional deployment automation** through Git integration, Fabric REST APIs, or workspace deployment pipelines.

---

## Core Design Principles
1. **Metadata-driven orchestration**  
   Pipelines should be generated and governed from metadata tables rather than manually authored for every source.

2. **Separation of concerns**  
   - **Bronze/Ingest** handles extraction and raw landing only.
   - **Silver** handles standardization, conformance, and reusable transformations.
   - **Gold** handles business-serving models and presentation logic.

3. **Idempotent discovery and upsert behavior**  
   The system should safely re-scan the same SQL definitions repeatedly and only insert or update changed metadata.

4. **Progressive automation**  
   Start with source discovery and ingest generation; extend later to silver and gold by reusing lineage metadata and transformation patterns.

5. **Human-in-the-loop for exceptions**  
   Not every SQL pattern can be auto-classified confidently. Provide a review queue for ambiguous parsing and unsupported sources.

---

## Target End State
The final operating model should work like this:

1. A scheduled Fabric Pipeline copies current production SQL definitions into a metadata landing zone.
2. A Fabric Notebook parses every SQL object using `sqlglot` (or a similar parser).
3. The notebook extracts:
   - source tables
   - source schemas/catalogs
   - referenced columns when possible
   - dependency lineage
   - query type and transformation complexity
4. Metadata is upserted into control tables.
5. Another notebook or orchestration step compares discovered source tables against currently registered ingest assets.
6. New or changed sources are routed through rules that determine:
   - ingestion method
   - load strategy (full, incremental, CDC, snapshot)
   - partitioning strategy
   - target bronze structure
   - refresh frequency
7. Fabric Pipelines execute parameterized Copy activities or notebook-based ingest jobs for each approved source.
8. Downstream silver and gold jobs use the same metadata tables plus lineage information to automate standard transformation scaffolding.

---

## Recommended Architecture

### 1. SQL Definition Ingestion Layer
Create a repeatable process that collects all production SQL definitions into Fabric.

**Potential sources of SQL definitions:**
- Stored procedures
- View definitions
- ELT scripts in Git
- SQL files from deployment repositories
- Warehouse/Lakehouse SQL endpoints
- Existing orchestration tool exports

**Recommended implementation:**
- A **Fabric Pipeline** runs on a schedule.
- Use a **Copy activity**, Notebook, or REST/API extraction step to land SQL definitions into a raw control area.
- Persist each object version into a table like `meta_sql_definitions_raw`.

**Suggested schema:**
- `object_id`
- `object_name`
- `object_type` (view, procedure, script, model)
- `source_system`
- `environment`
- `sql_text`
- `definition_hash`
- `retrieved_at_utc`
- `is_active`

This makes the process auditable, replayable, and versionable.

---

### 2. SQL Parsing and Metadata Extraction Layer
Use a **Fabric Notebook** in Python to parse the SQL text.

**Primary library:**
- `sqlglot`

**Notebook responsibilities:**
- Normalize SQL text.
- Parse CTEs and nested subqueries.
- Extract base source tables.
- Distinguish physical source tables from derived aliases and CTE names.
- Capture joins, unions, filters, and aggregation indicators.
- Optionally extract columns used from each source.
- Store parser confidence and exception details.

**Important output tables:**

### `meta_sql_objects`
One row per SQL object.
- `sql_object_key`
- `object_name`
- `object_type`
- `definition_hash`
- `parse_status`
- `parse_confidence`
- `complexity_score`
- `last_parsed_at_utc`

### `meta_sql_dependencies`
One row per object-to-source dependency.
- `sql_object_key`
- `dependency_type` (table, view, external table)
- `source_catalog`
- `source_schema`
- `source_table`
- `source_fqn`
- `discovered_via` (direct, cte_subquery, nested_subquery)
- `is_physical_source`

### `meta_source_inventory`
One row per unique source table.
- `source_fqn`
- `source_system`
- `first_seen_at_utc`
- `last_seen_at_utc`
- `active_object_count`
- `ingest_status`
- `bronze_target`
- `ingest_pattern`
- `review_status`

### `meta_sql_columns` *(future-ready)*
One row per object/source/column reference.
- `sql_object_key`
- `source_fqn`
- `column_name`
- `usage_type` (select, join, filter, group_by)

This aligns with your idea of maintaining a unique-source-table registry and leaves room to add field-level lineage later.

---

## Example Parsing Logic
For each production SQL object:

1. Read `sql_text`.
2. Parse with `sqlglot.parse_one()`.
3. Traverse the AST.
4. Build a set of:
   - CTE names
   - referenced tables/views
   - aliases
5. Exclude CTE aliases from the final physical source list.
6. Resolve the remaining base objects to fully qualified names where possible.
7. Upsert results into dependency and inventory tables.

**Best practice:** assign a `definition_hash` to each SQL body and skip re-parsing unchanged definitions unless forced.

---

## 3. Source Classification and Ingest Rule Engine
Once unique source tables are discovered, classify how each one should be ingested.

Create a metadata table like `meta_ingest_rules` with rules such as:
- source system = SQL Server -> use Copy activity
- source system = SAP extract -> use staged file landing
- source table size > threshold -> use partitioned ingest
- table contains `ModifiedDate` -> use incremental watermark
- CDC enabled -> use CDC pattern
- no change tracking -> schedule snapshot or full reload

**Suggested rule inputs:**
- source system
- connection type
- estimated volume
- available keys
- watermark column availability
- SLA tier
- refresh frequency
- source criticality

**Suggested outputs:**
- `ingest_pattern`
- `load_type`
- `watermark_column`
- `partition_column`
- `parallelism`
- `target_bronze_table`
- `file_format`
- `retention_policy`

This layer is what prevents the system from simply listing tables and instead turns discovery into actual automation.

---

## 4. Bronze/Ingest Automation Layer
This is the operational automation layer that provisions or drives ingestion.

### Recommended pattern: Metadata-driven master pipeline
Build one **master Fabric Pipeline** with the following flow:

1. Read `meta_source_inventory` for approved sources.
2. Filter where:
   - `ingest_status = 'READY'`
   - source is new or changed
   - refresh window is due
3. For each source, call a parameterized child pipeline or notebook.
4. Child pipeline executes the source-specific ingest pattern.
5. Update audit/control tables with success/failure metrics.

### Child pipeline options
**Option A: Copy activity-based ingest**
Best for relational and file sources with straightforward extraction.

**Option B: Notebook-based ingest**
Best for advanced logic, dynamic SQL generation, schema drift handling, and custom transformations.

**Option C: Dataflow Gen2 template-based ingest**
Useful when business users or low-code teams need to participate.

### Bronze landing standards
All bronze objects should use a consistent standard:
- raw schema preservation
- ingestion timestamp
- source system identifier
- batch/run identifier
- source extract timestamp if available
- optional row hash for change comparison

**Recommended bronze metadata columns:**
- `_ingest_run_id`
- `_ingest_ts_utc`
- `_source_system`
- `_source_object`
- `_load_type`
- `_record_hash`

---

## 5. Control, Audit, and Observability Layer
A robust system design must be easy to operate.

### Required control tables

#### `ctl_ingest_runs`
- `run_id`
- `pipeline_name`
- `started_at_utc`
- `ended_at_utc`
- `status`
- `trigger_type`

#### `ctl_ingest_run_details`
- `run_id`
- `source_fqn`
- `target_table`
- `rows_read`
- `rows_written`
- `watermark_start`
- `watermark_end`
- `status`
- `error_message`

#### `ctl_review_queue`
- `review_item_id`
- `item_type`
- `item_key`
- `reason`
- `severity`
- `status`
- `assigned_to`

### Monitoring recommendations
- Fabric monitoring for pipeline/notebook status
- Workspace alerts for repeated failures
- Daily exceptions summary notebook or Power BI report
- Parse-failure dashboard for unsupported SQL patterns

---

## 6. Governance and Change Management
Automation should not create unexpected production assets without controls.

### Recommended approval states for discovered sources
- `DISCOVERED`
- `PENDING_REVIEW`
- `READY`
- `BLOCKED`
- `RETIRED`

### Suggested lifecycle
1. New table discovered from a production query.
2. System inserts it into `meta_source_inventory` as `DISCOVERED`.
3. Rules attempt auto-classification.
4. If confidence is high, mark `READY`; otherwise send to review queue.
5. Approved sources are picked up by the master ingest pipeline.

This gives you automation without losing governance.

---

## Proposed End-to-End Workflow

### Phase A: Collect SQL definitions
**Fabric Pipeline: `PL_META_SQL_COLLECT`**
- Pull SQL definitions from repositories, views, procedures, or metadata stores.
- Land in `meta_sql_definitions_raw`.

### Phase B: Parse and discover dependencies
**Fabric Notebook: `NB_PARSE_SQL_DEPENDENCIES`**
- Use `sqlglot` to parse each SQL object.
- Upsert into `meta_sql_objects`, `meta_sql_dependencies`, and `meta_source_inventory`.
- Push ambiguous cases to `ctl_review_queue`.

### Phase C: Classify new sources
**Fabric Notebook: `NB_CLASSIFY_SOURCES`**
- Join source inventory to connection/system metadata.
- Apply ingest rules.
- Recommend ingest pattern and load type.
- Mark high-confidence sources as `READY`.

### Phase D: Execute bronze ingestion
**Fabric Pipeline: `PL_BRONZE_INGEST_MASTER`**
- Read all `READY` sources due for refresh.
- For each source, invoke:
  - `PL_BRONZE_COPY_CHILD`, or
  - `NB_BRONZE_INGEST_DYNAMIC`
- Log metrics to control tables.

### Phase E: Validate ingestion
**Fabric Notebook: `NB_VALIDATE_BRONZE_LOAD`**
- Row count checks
- schema validation
- duplicate key checks
- null threshold checks on critical fields

### Phase F: Trigger silver and gold downstream
Once bronze loads succeed, downstream orchestration can be triggered conditionally based on lineage.

---

## Practical Fabric Implementation Pattern

### Workspace assets to create
1. **Lakehouse or Warehouse for metadata/control tables**
2. **Pipeline for SQL metadata collection**
3. **Notebook for SQL parsing**
4. **Notebook for classification and upsert logic**
5. **Master bronze ingest pipeline**
6. **Child ingest pipeline or dynamic ingest notebook**
7. **Power BI/Fabric report for observability**

### Recommended metadata domains
- `meta_*` -> discovered metadata and lineage
- `ctl_*` -> execution control and audits
- `cfg_*` -> configurable rules and source definitions
- `brz_*` -> bronze landing assets
- `slv_*` -> silver assets
- `gld_*` -> gold assets

---

## How to Handle Complex SQL Reliably
Your use case explicitly includes complex CTE queries with subqueries. To make that reliable:

### Parsing robustness recommendations
- Normalize SQL dialect before parsing where possible.
- Store the original SQL plus normalized SQL.
- Keep parser exception text for unsupported constructs.
- Maintain a fallback regex-based extractor only for review assistance, not for production lineage truth.
- Track parser confidence scores.

### Confidence scoring example
- **High confidence**: all references fully parsed, no unresolved objects
- **Medium confidence**: partial parse, but probable physical sources isolated
- **Low confidence**: parser errors, dynamic SQL, unresolved identifiers

Low-confidence outputs should go to a review queue instead of auto-provisioning ingestion.

---

## Future Automation for Silver Layer
Yes, the same framework can be extended into silver automation.

### Silver automation opportunity
After bronze ingestion, the metadata store already knows:
- what source tables exist
- which production objects depend on them
- what joins/filters/aggregations appear repeatedly
- which columns are used in select/filter/group/join logic

### Silver automation patterns
1. **Standardization templates**
   Auto-generate notebooks or SQL scripts that:
   - cast datatypes
   - rename columns to standards
   - deduplicate on business keys
   - enforce null/default rules
   - conform timestamps and time zones

2. **Conformed entity generation**
   If multiple downstream queries repeatedly use the same source combinations, generate candidate silver entities automatically.

3. **Reusable transform macros**
   Build a library of common transformations:
   - SCD handling
   - late-arriving dimension logic
   - CDC merge logic
   - surrogate key generation

4. **Transformation pattern mining**
   Analyze existing SQL definitions to identify repeated logic that should become shared silver models.

### Suggested silver metadata additions
- `meta_transform_patterns`
- `meta_business_keys`
- `meta_quality_rules`
- `meta_conformed_entities`

### Silver automation guardrail
Do not fully auto-publish silver models to production at first. Generate recommended assets and require review/approval before activation.

---

## Future Automation for Gold Layer
Gold automation is also possible, but should be more opinionated and governed.

### Gold automation opportunities
1. **Metric discovery**
   Parse existing reporting SQL to identify repeated measures, dimensions, and filters.

2. **Semantic model scaffolding**
   Generate starter gold tables or semantic model definitions based on repeated business logic.

3. **Data product templates**
   For common subject areas, generate:
   - curated fact tables
   - dimensions
   - KPI views
   - refresh orchestration patterns

### Gold metadata extensions
- `meta_metrics_catalog`
- `meta_dimension_usage`
- `meta_business_domains`
- `meta_serving_dependencies`

### Strong recommendation
Bronze can be highly automated, silver partially automated, and gold should remain strongly governed because business semantics drift faster than source ingestion patterns.

---

## Reference System Design

### Control flow summary
1. **Collect SQL definitions**
2. **Parse and extract dependencies**
3. **Upsert unique source inventory**
4. **Classify sources with rules**
5. **Provision/run bronze ingest**
6. **Validate and audit**
7. **Drive downstream silver/gold candidates from metadata**

### Data flow summary
- production SQL -> raw SQL metadata table
- raw SQL metadata -> parsed dependency tables
- dependency tables -> unique source inventory
- unique source inventory + rule tables -> ingest execution plan
- ingest execution plan -> bronze landing
- bronze lineage + transform metadata -> silver/gold automation

---

## Recommended MVP Roadmap

### MVP Phase 1: Discovery and inventory
Deliver first:
- SQL collection pipeline
- `sqlglot` parsing notebook
- `meta_source_inventory`
- review queue for low-confidence parsing

**Outcome:** complete inventory of real production source tables.

### MVP Phase 2: Bronze automation
Next deliver:
- ingest rule engine
- master bronze pipeline
- parameterized child pipelines/notebooks
- control and audit tables

**Outcome:** new and existing sources can be ingested from metadata with minimal manual work.

### MVP Phase 3: Schema and column intelligence
Add:
- source column profiling
- schema drift detection
- field-level lineage
- quality checks

**Outcome:** safer and more maintainable automation.

### MVP Phase 4: Silver recommendations
Add:
- repeated transformation detection
- conformed entity suggestions
- generated silver templates

**Outcome:** partial automation of transformation engineering.

### MVP Phase 5: Gold recommendations
Add:
- metric extraction
- semantic layer scaffolding
- business-domain data product templates

**Outcome:** assisted automation for analytics-serving layers.

---

## Risks and Mitigations

### Risk: SQL parser cannot fully resolve every query
**Mitigation:** confidence scoring, exception logging, and review queue.

### Risk: Too many false-positive sources
**Mitigation:** exclude CTE aliases, temp objects, and known derived object patterns.

### Risk: Auto-generated ingest jobs become difficult to govern
**Mitigation:** require metadata approval states and full audit logging.

### Risk: Source systems need different extraction patterns
**Mitigation:** rule engine plus child-pipeline strategy pattern.

### Risk: Silver/gold automation creates incorrect business logic
**Mitigation:** keep downstream automation advisory-first, then approval-gated.

---

## Recommendation
Your idea is directionally correct and strong: **scan all production SQL, parse with `sqlglot`, upsert distinct source tables into a metadata inventory, and drive ingest from that inventory**.

The most effective enterprise-grade version of that idea is:
- **Fabric Pipeline** to collect SQL definitions
- **Fabric Notebook with `sqlglot`** to parse lineage from CTE-heavy SQL
- **Metadata/control tables** to store source inventory, dependencies, rules, and audit state
- **Master metadata-driven bronze ingest pipeline** to operationalize onboarding
- **Review queue and confidence scoring** to keep the system robust
- **Lineage-driven extensions** to gradually automate silver and then gold

If you want the highest return on effort, prioritize this order:
1. SQL collection and parsing
2. unique source inventory and review workflow
3. rule-based bronze ingest automation
4. audit/observability
5. silver recommendations
6. gold recommendations

That sequence will remove the most manual work first while creating a durable foundation for broader Fabric automation.
