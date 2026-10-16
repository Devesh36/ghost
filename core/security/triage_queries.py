"""New Graph Hacks work: fixed, parameterized FalkorDB reasoning queries.

Scores and ordering are computed by the graph, never by a Python fallback.
"""

RANK = """
MATCH (d:GhostTriageDemo {id: $dataset, version: 1, ready: true})
MATCH (f:Finding {dataset: $dataset})
OPTIONAL MATCH (f)-[:AFFECTS]->(p:Package {dataset: $dataset})
OPTIONAL MATCH (s:Service {dataset: $dataset})-[:USES]->(p)
OPTIONAL MATCH (s)-[:EXPOSED_TO]->(e:Exposure {dataset: $dataset, id: 'internet'})
WITH f, count(DISTINCT s) AS services,
     count(DISTINCT CASE WHEN e IS NOT NULL THEN s ELSE null END) AS public_services
OPTIONAL MATCH (f)-[:LINKED_TO]->(i:Incident {dataset: $dataset, status: 'open'})
WITH f, services, public_services, count(DISTINCT i) AS open_incidents
WITH f, services, public_services, open_incidents,
     CASE f.severity WHEN 'HIGH' THEN 30 WHEN 'MEDIUM' THEN 20
          WHEN 'LOW' THEN 10 ELSE 0 END AS severity_points,
     40 * public_services AS exposure_points,
     50 * open_incidents AS incident_points, 5 * services AS service_points
RETURN f.id AS finding_id, f.title AS title, f.rule AS rule,
       f.severity AS severity, f.confidence AS confidence, f.state AS state,
       services, public_services, open_incidents,
       severity_points, exposure_points, incident_points, service_points,
       severity_points + exposure_points + incident_points + service_points AS score
ORDER BY score DESC, public_services DESC, open_incidents DESC, finding_id ASC
LIMIT 20
"""

SERVICE_PATHS = """
MATCH (f:Finding {dataset: $dataset, id: $finding})
OPTIONAL MATCH (f)-[:AFFECTS]->(p:Package {dataset: $dataset})
OPTIONAL MATCH (s:Service {dataset: $dataset})-[:USES]->(p)
OPTIONAL MATCH (s)-[:EXPOSED_TO]->(e:Exposure {dataset: $dataset, id: 'internet'})
OPTIONAL MATCH (t:Team {dataset: $dataset})-[:OWNS]->(s)
RETURN DISTINCT f.id AS finding_id, p.id AS package_id, p.name AS package_name,
       s.id AS service_id, s.name AS service_name, e.id AS exposure,
       t.id AS team_id, t.name AS team_name
ORDER BY package_id, service_id, team_id
LIMIT 200
"""

INCIDENT_PATHS = """
MATCH (f:Finding {dataset: $dataset, id: $finding})-[:LINKED_TO]->(i:Incident {dataset: $dataset})
RETURN DISTINCT f.id AS finding_id, i.id AS incident_id, i.name AS title, i.status AS status
ORDER BY incident_id
LIMIT 20
"""
