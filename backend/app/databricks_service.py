"""Databricks SQL Warehouse integration for Security Intelligence Layer.

Connects to Databricks SQL Warehouse using the SQL Statements API.
Fetches intelligence data from main.default.hof_intelligence_layer table.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

DATABRICKS_API_BASE = "https://{hostname}/api/2.0/sql/statements"


def _get_databricks_config() -> tuple[str, str, str] | None:
    """Get Databricks configuration from environment variables.
    Returns (hostname, http_path, token) or None if missing."""
    hostname = os.environ.get("DATABRICKS_SERVER_HOSTNAME", "").strip()
    http_path = os.environ.get("DATABRICKS_HTTP_PATH", "").strip()
    token = os.environ.get("DATABRICKS_TOKEN", "").strip()
    
    if not hostname or not http_path or not token:
        logger.warning("DATABRICKS_SERVER_HOSTNAME / DATABRICKS_HTTP_PATH / DATABRICKS_TOKEN not set")
        logger.debug(f"Hostname: {hostname[:20] if hostname else 'None'}...")
        logger.debug(f"HTTP Path: {http_path[:30] if http_path else 'None'}...")
        logger.debug(f"Token: {'***' + token[-4:] if token else 'None'}")
        return None
    
    logger.debug(f"Databricks config loaded: hostname={hostname[:20]}..., path={http_path[:30]}...")
    return hostname, http_path, token


def execute_sql_query(sql: str, limit: int = 20) -> list[dict]:
    """Execute a SQL query against Databricks SQL Warehouse.
    
    Args:
        sql: SQL query string
        limit: Maximum number of rows to return
        
    Returns:
        List of row dictionaries, or empty list on error.
    """
    try:
        config = _get_databricks_config()
        if not config:
            logger.error("Databricks configuration is missing")
            raise ValueError("Databricks configuration is missing. Check environment variables.")
        
        hostname, http_path, token = config
    except Exception as e:
        logger.error(f"Failed to get Databricks config: {e}")
        raise
    
    url = DATABRICKS_API_BASE.format(hostname=hostname)
    
    # Extract warehouse ID from HTTP path: /sql/1.0/warehouses/{warehouse_id}
    # Path format: /sql/1.0/warehouses/99e25fa26b7ed67d
    warehouse_id = http_path.split("/")[-1] if "/" in http_path else http_path
    
    payload = {
        "warehouse_id": warehouse_id,
        "statement": sql,
        "wait_timeout": "30s",
        "on_wait_timeout": "CANCEL"
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        logger.debug(f"Executing SQL query: {sql[:200]}...")
        logger.debug(f"Request URL: {url}")
        logger.debug(f"Warehouse ID: {warehouse_id}")
        logger.debug(f"Payload: {payload}")
        
        response = requests.post(url, json=payload, headers=headers, timeout=45)
        logger.debug(f"Response status: {response.status_code}")
        
        if response.status_code != 200:
            error_text = response.text[:500] if response.text else "No error message"
            logger.error(f"Databricks API error {response.status_code}: {error_text}")
            raise requests.exceptions.HTTPError(f"Databricks API returned {response.status_code}: {error_text}")
        
        result = response.json()
        logger.debug(f"Response keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
        
        # Parse the result structure from Databricks SQL Statements API
        if "result" in result:
            result_data = result["result"]
            
            # Get column names from schema
            columns = []
            if "schema" in result_data and "columns" in result_data["schema"]:
                columns = [col.get("name", f"col_{i}") for i, col in enumerate(result_data["schema"]["columns"])]
            
            # Get data rows
            rows = result_data.get("data_array", [])
            
            # Convert to list of dicts
            if columns and rows:
                return [dict(zip(columns, row)) for row in rows[:limit]]
            elif rows:
                # Fallback: use generic column names if schema missing
                return [dict(zip([f"col_{i}" for i in range(len(row))], row)) for row in rows[:limit]]
        
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Databricks HTTP request failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text[:500]}")
        raise  # Re-raise to be caught by main endpoint
    except Exception as e:
        logger.exception("Databricks SQL query failed: %s", e)
        raise  # Re-raise to be caught by main endpoint


def _get_mock_intelligence_data(user_email: str | None = None) -> list[dict]:
    """Generate mock intelligence data matching the PySpark structure for demo purposes."""
    ADMIN_EMAIL = 'mr6761@nyu.edu'
    is_admin = user_email and user_email.strip().lower() == ADMIN_EMAIL.lower()
    
    # Mock data matching the PySpark example structure
    mock_data = [
        {
            "person_name": "John Doe" if is_admin else "🔒 [RESTRICTED]",
            "person_role": "Visitor" if is_admin else "🔒 [RESTRICTED]",
            "alert_type": "restricted_access",
            "infraction_sentence": "Detected in Server Room B.",
            "escalation_level": "CRITICAL",
            "timestamp": "2026-02-22 05:00:00",
            "threat_score": 80,
            "is_repeat_offender": True,
            "ai_analysis": "Multiple security violations detected. Subject has attempted unauthorized access to restricted areas on multiple occasions. Recommend immediate security review."
        },
        {
            "person_name": "John Doe" if is_admin else "🔒 [RESTRICTED]",
            "person_role": "Visitor" if is_admin else "🔒 [RESTRICTED]",
            "alert_type": "unauthorized_entry",
            "infraction_sentence": "Keycard rejected at North Vault.",
            "escalation_level": "URGENT",
            "timestamp": "2026-02-22 05:15:00",
            "threat_score": 65,
            "is_repeat_offender": True,
            "ai_analysis": "Repeated unauthorized access attempts. Subject appears to be testing security boundaries."
        },
        {
            "person_name": "John Doe" if is_admin else "🔒 [RESTRICTED]",
            "person_role": "Visitor" if is_admin else "🔒 [RESTRICTED]",
            "alert_type": "zone_breach",
            "infraction_sentence": "Loitering in parking lot.",
            "escalation_level": "ROUTINE",
            "timestamp": "2026-02-22 05:45:00",
            "threat_score": 50,
            "is_repeat_offender": True,
            "ai_analysis": "Suspicious loitering behavior detected. Subject has been flagged multiple times."
        },
        {
            "person_name": "Sarah Jenkins" if is_admin else "🔒 [RESTRICTED]",
            "person_role": "Analyst" if is_admin else "🔒 [RESTRICTED]",
            "alert_type": "tailgating",
            "infraction_sentence": "Followed staff into secure lift.",
            "escalation_level": "URGENT",
            "timestamp": "2026-02-22 05:05:00",
            "threat_score": 70,
            "is_repeat_offender": False,
            "ai_analysis": "Tailgating incident detected. Subject followed authorized personnel into secure area without proper clearance."
        },
        {
            "person_name": "Michael Chen" if is_admin else "🔒 [RESTRICTED]",
            "person_role": "Contractor" if is_admin else "🔒 [RESTRICTED]",
            "alert_type": "restricted_access",
            "infraction_sentence": "Accessed HVAC room after hours.",
            "escalation_level": "CRITICAL",
            "timestamp": "2026-02-22 05:10:00",
            "threat_score": 75,
            "is_repeat_offender": False,
            "ai_analysis": "Critical security breach. Contractor accessed restricted infrastructure area outside authorized hours."
        }
    ]
    
    # Sort by threat_score descending
    mock_data.sort(key=lambda x: x.get("threat_score", 0), reverse=True)
    
    return mock_data


def get_security_intelligence(limit: int = 20, user_email: str | None = None) -> list[dict]:
    """Fetch security intelligence data from hof_intelligence_layer table.
    
    Args:
        limit: Maximum number of records to return
        user_email: User email for dynamic masking. If 'mr6761@nyu.edu', reveals all data.
                    Otherwise, person_name and person_role are masked with 🔒 [RESTRICTED].
    
    Returns list of intelligence records, sorted by threat_score descending.
    """
    ADMIN_EMAIL = 'mr6761@nyu.edu'
    
    # Sanitize email input to prevent SQL injection
    if user_email:
        import re
        safe_email = re.sub(r'[^a-zA-Z0-9@.\-_]', '', user_email.strip().lower())
    else:
        safe_email = 'guest@restricted.local'
    
    is_admin = safe_email == ADMIN_EMAIL.lower()
    
    # Try to get real data from Databricks first
    # Match PySpark notebook structure: use security_feed view with apply_mask UDF
    try:
        # Build SQL matching PySpark notebook exactly
        # Try security_feed view first (from PySpark notebook), then fallback to hof_intelligence_layer
        # Simplified: try security_feed first, if it fails, try hof_intelligence_layer
        if is_admin:
            # Admin: no masking needed - try security_feed first
            sql = f"""
            SELECT 
                person_name,
                person_role,
                alert_type,
                infraction_sentence,
                escalation_level,
                timestamp,
                threat_score,
                is_repeat_offender,
                COALESCE(ai_analysis, infraction_sentence) as ai_analysis
            FROM main.default.security_feed
            ORDER BY threat_score DESC 
            LIMIT {limit}
            """
        else:
            # Guest: Use apply_mask UDF (from PySpark notebook) or CASE fallback
            # This matches the PySpark notebook logic: apply_mask(person_name, email)
            sql = f"""
            SELECT 
                COALESCE(
                    apply_mask(person_name, '{safe_email}'),
                    CASE 
                        WHEN '{safe_email}' = '{ADMIN_EMAIL.lower()}' THEN person_name 
                        ELSE '🔒 [RESTRICTED]'
                    END
                ) as person_name,
                COALESCE(
                    apply_mask(person_role, '{safe_email}'),
                    CASE 
                        WHEN '{safe_email}' = '{ADMIN_EMAIL.lower()}' THEN person_role 
                        ELSE '🔒 [RESTRICTED]'
                    END
                ) as person_role,
                alert_type,
                infraction_sentence,
                escalation_level,
                timestamp,
                threat_score,
                is_repeat_offender,
                COALESCE(ai_analysis, infraction_sentence) as ai_analysis
            FROM main.default.security_feed
            ORDER BY threat_score DESC 
            LIMIT {limit}
            """
        
        try:
            data = execute_sql_query(sql, limit=limit)
            if data:
                logger.info(f"Retrieved {len(data)} records from Databricks security_feed view")
                return data
        except Exception as view_error:
            logger.debug(f"security_feed view not available, trying hof_intelligence_layer: {view_error}")
            # Fallback to hof_intelligence_layer table
            if is_admin:
                sql = f"""
                SELECT 
                    person_name,
                    person_role,
                    alert_type,
                    infraction_sentence,
                    escalation_level,
                    timestamp,
                    threat_score,
                    is_repeat_offender,
                    COALESCE(ai_analysis, infraction_sentence) as ai_analysis
                FROM main.default.hof_intelligence_layer
                ORDER BY threat_score DESC 
                LIMIT {limit}
                """
            else:
                sql = f"""
                SELECT 
                    CASE 
                        WHEN '{safe_email}' = '{ADMIN_EMAIL.lower()}' THEN person_name 
                        ELSE '🔒 [RESTRICTED]'
                    END as person_name,
                    CASE 
                        WHEN '{safe_email}' = '{ADMIN_EMAIL.lower()}' THEN person_role 
                        ELSE '🔒 [RESTRICTED]'
                    END as person_role,
                    alert_type,
                    infraction_sentence,
                    escalation_level,
                    timestamp,
                    threat_score,
                    is_repeat_offender,
                    COALESCE(ai_analysis, infraction_sentence) as ai_analysis
                FROM main.default.hof_intelligence_layer
                ORDER BY threat_score DESC 
                LIMIT {limit}
                """
            try:
                data = execute_sql_query(sql, limit=limit)
                if data:
                    logger.info(f"Retrieved {len(data)} records from Databricks hof_intelligence_layer table")
                    return data
            except Exception as table_error:
                logger.warning(f"Both security_feed and hof_intelligence_layer failed: {table_error}")
                raise
        
        # If we got here, no data was returned
        logger.warning("No data from Databricks, using mock data")
        return _get_mock_intelligence_data(user_email)[:limit]
            
    except Exception as e:
        logger.warning(f"Databricks query failed, using mock data: {e}")
        # Return mock data when Databricks is unavailable
        return _get_mock_intelligence_data(user_email)[:limit]


def call_genie_api(prompt: str, viewer_email: str) -> dict:
    """Call Databricks Genie API to get AI-generated responses.
    
    Args:
        prompt: User's question/prompt
        viewer_email: Email for clearance context (used for masking)
    
    Returns:
        Dict with 'message', 'sql_query', and optionally 'error'
    """
    logger.info("=" * 80)
    logger.info("CALL_GENIE_API CALLED")
    logger.info(f"Prompt: {prompt[:200]}")
    logger.info(f"Viewer email: {viewer_email}")
    
    # Check if Databricks is configured - NO MOCK FALLBACK
    try:
        logger.info("🔍 Checking Databricks configuration...")
        config = _get_databricks_config()
        if not config:
            error_msg = "Databricks configuration is missing. Set DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, and DATABRICKS_TOKEN in .env"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
        
        hostname, _, token = config
        logger.info(f"✅ Databricks config found: hostname={hostname[:30]}...")
        logger.info(f"Token present: {bool(token)}")
        logger.info(f"Token preview: {'***' + token[-4:] if token else 'None'}")
    except Exception as e:
        logger.error(f"❌ Failed to get Databricks config: {e}")
        logger.exception("Config error details:")
        raise  # Don't return mock, raise the error
    
    # Genie Room ID from user's URL
    GENIE_ROOM_ID = "01f10fea98a51457bcb5737bd9a4501b"
    url = f"https://{hostname}/api/2.0/genie/rooms/{GENIE_ROOM_ID}/messages"
    
    payload = {
        "content": prompt,
        "context": {"viewer_email": viewer_email}
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    logger.info(f"🌐 Genie API URL: {url}")
    logger.info(f"📦 Payload: {payload}")
    logger.info(f"🔑 Headers: Authorization=Bearer ***, Content-Type=application/json")
    
    try:
        logger.info("🔄 Sending POST request to Genie API...")
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        logger.info(f"📥 Response received: status={response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            error_text = response.text[:1000] if response.text else "No error message"
            logger.error(f"❌ Genie API error {response.status_code}")
            logger.error(f"Error response: {error_text}")
            raise requests.exceptions.HTTPError(f"Genie API returned {response.status_code}: {error_text}")
        
        logger.info("✅ Parsing JSON response...")
        try:
            result = response.json()
            logger.info(f"✅ JSON parsed successfully")
            logger.info(f"Response keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
            logger.info(f"Full response: {str(result)[:500]}")
        except Exception as json_err:
            logger.error(f"❌ Failed to parse JSON: {json_err}")
            logger.error(f"Response text: {response.text[:500]}")
            raise ValueError(f"Failed to parse Genie API response: {json_err}")
        
        # Extract message and SQL query from Genie response
        logger.info("🔍 Extracting message and SQL query from response...")
        message = result.get("message") or result.get("content") or result.get("response", "")
        sql_query = result.get("sql_query") or result.get("sql") or result.get("query", None)
        
        logger.info(f"Message found: {bool(message)}, length: {len(message) if message else 0}")
        logger.info(f"SQL query found: {bool(sql_query)}")
        
        # Try to extract SQL from message if it's embedded
        if not sql_query and message:
            logger.info("🔍 Attempting to extract SQL from message...")
            import re
            sql_match = re.search(r'```sql\s*(.*?)\s*```', message, re.DOTALL | re.IGNORECASE)
            if sql_match:
                sql_query = sql_match.group(1).strip()
                logger.info("✅ SQL extracted from code block")
            else:
                # Try without code blocks
                sql_match = re.search(r'(SELECT.*?;)', message, re.DOTALL | re.IGNORECASE)
                if sql_match:
                    sql_query = sql_match.group(1).strip()
                    logger.info("✅ SQL extracted from message text")
                else:
                    logger.info("ℹ️ No SQL found in message")
        
        final_result = {
            "message": message,
            "sql_query": sql_query,
            "raw_response": result  # Include full response for debugging
        }
        logger.info(f"✅ Returning result: message={bool(final_result['message'])}, sql_query={bool(final_result['sql_query'])}")
        logger.info("=" * 80)
        return final_result
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Genie HTTP request failed: {type(e).__name__}")
        logger.exception(f"Request exception details: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text[:500]}")
        logger.info("=" * 80)
        raise  # Re-raise the exception, no mock fallback
    except Exception as e:
        logger.error(f"❌ Genie API call failed: {type(e).__name__}")
        logger.exception(f"Exception details: {e}")
        logger.info("=" * 80)
        raise  # Re-raise the exception, no mock fallback


def _get_mock_genie_response(prompt: str, viewer_email: str) -> dict:
    """Generate a mock Genie response when Databricks is unavailable.
    
    This provides a helpful response based on common queries.
    """
    prompt_lower = prompt.lower()
    
    # Simple pattern matching for common queries
    if "top offender" in prompt_lower or ("who is" in prompt_lower and ("offender" in prompt_lower or "threat" in prompt_lower)):
        message = "Based on the security intelligence data, the top offender appears to be a repeat visitor with multiple CRITICAL level violations. Threat score analysis shows patterns of unauthorized access attempts."
        sql_query = "SELECT person_name, COUNT(*) as incident_count, MAX(threat_score) as max_threat_score FROM main.default.hof_intelligence_layer GROUP BY person_name ORDER BY max_threat_score DESC, incident_count DESC LIMIT 1"
    elif "critical" in prompt_lower and ("today" in prompt_lower or "count" in prompt_lower or "how many" in prompt_lower):
        if "how many" in prompt_lower or "count" in prompt_lower:
            message = "Based on today's data, there are 3 critical alerts identified. These include restricted access violations and unauthorized entry attempts requiring immediate security review."
            sql_query = "SELECT COUNT(*) as critical_count FROM main.default.hof_intelligence_layer WHERE escalation_level = 'CRITICAL' AND DATE(timestamp) = CURRENT_DATE"
        else:
            message = "Today's critical alerts show multiple restricted access violations and unauthorized entry attempts. The escalation level indicates immediate security review is recommended."
            sql_query = "SELECT * FROM main.default.hof_intelligence_layer WHERE escalation_level = 'CRITICAL' AND DATE(timestamp) = CURRENT_DATE ORDER BY threat_score DESC"
    elif "how many" in prompt_lower and "critical" in prompt_lower:
        message = "Based on the intelligence layer, there are currently 3 critical alerts. These represent the highest threat level incidents requiring immediate attention."
        sql_query = "SELECT COUNT(*) as critical_count FROM main.default.hof_intelligence_layer WHERE escalation_level = 'CRITICAL'"
    elif "risk velocity" in prompt_lower or "velocity" in prompt_lower:
        message = "Risk velocity analysis indicates an increasing trend in security incidents. The rate of repeat offenses suggests potential systematic security testing."
        sql_query = "SELECT DATE(timestamp) as incident_date, COUNT(*) as daily_incidents, AVG(threat_score) as avg_threat FROM main.default.hof_intelligence_layer GROUP BY DATE(timestamp) ORDER BY incident_date DESC LIMIT 7"
    elif "repeat" in prompt_lower or "offender" in prompt_lower:
        message = "Repeat offender analysis shows 2 individuals with multiple security violations. These patterns indicate potential systematic security testing or persistent unauthorized access attempts."
        sql_query = "SELECT person_name, COUNT(*) as incident_count, MAX(threat_score) as max_threat FROM main.default.hof_intelligence_layer WHERE is_repeat_offender = true GROUP BY person_name ORDER BY incident_count DESC"
    elif "threat" in prompt_lower and ("score" in prompt_lower or "level" in prompt_lower):
        message = "Threat score analysis shows a range from 40 to 80, with the highest scores associated with CRITICAL escalation levels. The average threat score across all incidents is approximately 65."
        sql_query = "SELECT AVG(threat_score) as avg_threat, MIN(threat_score) as min_threat, MAX(threat_score) as max_threat FROM main.default.hof_intelligence_layer"
    elif "alert" in prompt_lower and ("today" in prompt_lower or "recent" in prompt_lower):
        message = "Recent alerts show a mix of CRITICAL, URGENT, and ROUTINE escalation levels. The most common alert types are restricted_access and unauthorized_entry."
        sql_query = "SELECT alert_type, escalation_level, COUNT(*) as count FROM main.default.hof_intelligence_layer WHERE DATE(timestamp) >= CURRENT_DATE - INTERVAL 1 DAY GROUP BY alert_type, escalation_level ORDER BY count DESC"
    else:
        message = f"I understand you're asking about: '{prompt}'. To provide accurate analysis, I would need to query the Databricks intelligence layer. Currently, the Genie API connection is not available, but I can help with general security intelligence queries. Try asking about: top offenders, critical alerts, risk velocity, or repeat offenders."
        sql_query = None
    
    return {
        "message": message,
        "sql_query": sql_query,
        "note": "This is a mock response. Connect to Databricks Genie for live analysis."
    }
