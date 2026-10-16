"""Graph Hacks recommendation, using Ghost's existing terminal palette."""
from rich.console import Console
from rich.text import Text

from config import theme
from core.security.graph_triage import TriageAnswer
from surfaces.shared.terminal.brief import bounded, review_card
from surfaces.shared.terminal.console import literal


def show_triage(answer: TriageAnswer, console: Console):
    console.print(Text('\nGhost / Graph Hacks / FalkorDB triage', style=f'bold {theme.TEXT}'))
    console.print(Text('SYNTHETIC DEMO / graph-derived priority / suspected findings', style=theme.WARNING))
    console.print(literal(answer.question, style=theme.MINT))
    winner = answer.recommendation
    body = Text(f'Fix first: {winner.finding_id} / {winner.score} points\n', style=f'bold {theme.MINT}')
    body += literal(bounded(winner.title))
    body.append(f'\n{winner.severity} / {winner.rule} / {winner.confidence} match confidence / SUSPECTED', style=theme.MUTED)
    body += literal('\nOwner: ' + (', '.join(answer.owners) or 'not recorded'), multiline=True)
    review_card(console, body, Text('FalkorDB recommendation'), color=theme.MINT)
    console.print(literal(answer.explanation, style=theme.TEXT))
    console.print(Text('\nRanking returned by FalkorDB', style=f'bold {theme.TEXT}'))
    for index, item in enumerate(answer.ranking, 1):
        console.print(literal(f'{index}. {item.finding_id} / {item.score} points / {item.severity} / {bounded(item.title)}'))
    console.print(Text('\nEvidence paths returned by graph queries', style=f'bold {theme.TEXT}'))
    for path in answer.evidence_paths:
        console.print(literal(path, style=theme.current().secondary))
    if not answer.evidence_paths:
        console.print(Text('No relationship context recorded; investigate before acting.', style=theme.WARNING))
    console.print(Text('\nQuery trace / GRAPH.RO_QUERY', style=theme.MUTED))
    for query in answer.query_trace:
        console.print(Text(f'{query.query_id}: {query.rows} rows', style=theme.MUTED))
    console.print(Text('Use ghost triage --json for the Cypher and full graph evidence.', style=theme.MINT))
    console.print(Text('\n' + answer.limits, style=theme.MUTED))
