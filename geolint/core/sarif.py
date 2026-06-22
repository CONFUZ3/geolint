"""
SARIF 2.1.0 output for GeoLint findings.

SARIF (Static Analysis Results Interchange Format) lets GeoLint findings surface
as GitHub code-scanning annotations on pull requests, the same way linters and
security scanners do.
"""

from typing import Dict, List

_SARIF_LEVEL = {'error': 'error', 'warning': 'warning', 'info': 'note', 'off': 'none'}

try:
    from geolint import __version__ as _VERSION
except Exception:  # pragma: no cover
    _VERSION = '0.0.0'


def to_sarif(findings: List[Dict], file_uri: str) -> Dict:
    """
    Convert findings to a SARIF 2.1.0 log.

    Args:
        findings: Findings from collect_findings.
        file_uri: The artifact URI (the validated file path) to attach results to.

    Returns:
        A SARIF log dict (JSON-serializable).
    """
    rules = {}
    results = []
    for f in findings:
        rule_id = f.get('check_id', 'unknown')
        if rule_id not in rules:
            rules[rule_id] = {
                'id': rule_id,
                'name': rule_id,
                'shortDescription': {'text': rule_id.replace('_', ' ')},
            }
        result = {
            'ruleId': rule_id,
            'level': _SARIF_LEVEL.get(f.get('severity', 'warning'), 'warning'),
            'message': {'text': f.get('message', rule_id)},
            'locations': [{
                'physicalLocation': {
                    'artifactLocation': {'uri': file_uri},
                }
            }],
        }
        locations = f.get('locations') or []
        if locations:
            result['properties'] = {'feature_indices': locations}
        results.append(result)

    return {
        '$schema': 'https://json.schemastore.org/sarif-2.1.0.json',
        'version': '2.1.0',
        'runs': [{
            'tool': {
                'driver': {
                    'name': 'GeoLint',
                    'informationUri': 'https://github.com/CONFUZ3/geolint',
                    'version': _VERSION,
                    'rules': list(rules.values()),
                }
            },
            'results': results,
        }],
    }
