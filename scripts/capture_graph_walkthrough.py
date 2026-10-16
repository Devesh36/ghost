"""Make a 60-second captioned video from freshly queried FalkorDB answers.

Run from checkout: python -m scripts.capture_graph_walkthrough
Requires the graph extra, local FalkorDB, Node with Playwright, and separately
installed chromium, ffmpeg and ffprobe. No tool binaries are bundled.
The video is an edited replay of real results, not a continuous screen recording.
"""
import argparse
import html
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from rich.console import Console
from rich.text import Text

from config import theme
from examples.graph_triage.walkthrough import walkthrough


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=6379)
    args = parser.parse_args()
    for executable in ('node', 'chromium', 'ffmpeg', 'ffprobe'):
        if not shutil.which(executable):
            parser.error(f'Install {executable} separately to regenerate the video.')
    theme.activate('ghost')
    output = Path('examples/graph_triage')
    report = walkthrough(args.port)
    stages = {stage['stage']: stage['answer'] for stage in report['stages']}
    before, after, restored = (stages[key] for key in ('baseline', 'incident_link_removed', 'restored'))

    def summary(answer):
        winner = answer['recommendation']
        return '\n'.join([
            f"Fix first: {winner['finding_id']} / {winner['score']} points",
            f"Owner: {', '.join(answer['owners'])}",
            '', answer['explanation'], '',
            *[f"{index}. {item['finding_id']} / {item['score']} points / {item['severity']}"
              for index, item in enumerate(answer['ranking'], 1)],
        ])

    slides = [
        ('01 / The question', 'Which finding should we fix first, and why?',
         'Ghost Graph Triage\n\n'
         'Severity alone misses operational context.\n\n'
         'Finding -> Package <- Service -> Internet\n'
         '                         ^\n'
         '                       Team\n'
         'Finding -> Incident\n\n'
         'FalkorDB traverses these connections, calculates the priority,\n'
         'and returns the ordered findings and evidence.\n\n'
         'One synthetic dataset. One question. No model call.'),
        ('02 / Real baseline result', 'The public API and open incident make F-002 first.', summary(before)),
        ('03 / Evidence from FalkorDB', 'Ghost follows the winning finding\'s relationships.',
         '\n\n'.join(before['evidence_paths']) + '\n\n'
         'Ranking, service evidence and incident evidence use GRAPH.RO_QUERY.\n'
         'Scores and ordering come from Cypher; Ghost does not sort locally.'),
        ('04 / Change one relationship', 'Remove F-002 -> INC-042. Ask the same question again.',
         summary(after) + '\n\nOnly the incident edge changed. F-002 falls from 115 to 65.\n'
         'The sample file and ranking policy are unchanged.'),
        ('05 / Restore and reproduce', 'Restore the edge. The original recommendation returns.',
         f"Actual restored result: {restored['recommendation']['finding_id']} / "
         f"{restored['recommendation']['score']} points\n\n"
         'uv run --locked --extra graph ghost triage --load-demo\n'
         'uv run --locked --extra graph python -m examples.graph_triage.walkthrough\n\n'
         'New: graph dataset, loader, Cypher ranking, evidence agent and demo.\n'
         'Reused: Ghost finding model, CLI/REPL and terminal theme.\n\n'
         'Source and setup: github.com/Devesh36/ghost\n'
         'docs/graph-hacks.md | docs/graph-hacks-submission.md\n\n'
         'Synthetic findings remain suspected. Event eligibility is unverified.'),
    ]
    with tempfile.TemporaryDirectory(prefix='ghost-graph-video-') as temp:
        directory = Path(temp)
        for index, (label, caption, body) in enumerate(slides):
            console = Console(file=io.StringIO(), width=98, record=True, color_system='truecolor')
            console.print(Text(body, style=theme.TEXT))
            exported = console.export_html(inline_styles=True)
            terminal = re.search(r'<pre.*?</pre>', exported, re.DOTALL).group()
            page = directory / f'{index}.html'
            page.write_text(f'''<!doctype html><html><meta charset="utf-8">
<title>Ghost graph walkthrough</title><style>
*{{box-sizing:border-box}}body{{margin:0;padding:48px;background:{theme.current().background};color:{theme.TEXT};font:22px/1.5 monospace}}
.label{{color:{theme.MINT};font-size:22px}}h1{{font:32px/1.3 monospace;margin:22px 0 32px}}
pre{{margin:0;white-space:pre-wrap;font:22px/1.5 monospace}}pre code{{font:inherit}}
footer{{position:absolute;bottom:32px;color:{theme.MUTED};font-size:18px}}
</style><div class="label">GHOST / FALKORDB / {html.escape(label)}</div>
<h1>{html.escape(caption)}</h1>{terminal}
<footer>SYNTHETIC DEMO · Real query results · Edited replay · {index+1}/5</footer></html>''')
        browser_script = r'''
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({executablePath: process.argv[2], args: ['--no-sandbox']});
  try {
    const page = await browser.newPage({viewport: {width: 1600, height: 1000}});
    await page.route('https://**/*', route => route.abort());
    await page.route('http://**/*', route => route.abort());
    for (let index = 0; index < 5; index++) {
      await page.setContent(fs.readFileSync(path.join(process.argv[1], `${index}.html`), 'utf8'));
      const fits = await page.evaluate(() => document.querySelector('pre').getBoundingClientRect().bottom
        < document.querySelector('footer').getBoundingClientRect().top
        && document.documentElement.scrollWidth <= innerWidth);
      if (!fits) throw new Error(`Slide ${index} overflows`);
      await page.screenshot({path: path.join(process.argv[1], `${index}.png`)});
    }
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exit(1);});
'''
        subprocess.run(['node', '-e', browser_script, str(directory), shutil.which('chromium')],
                       check=True, timeout=60)
        manifest = directory / 'frames.txt'
        manifest.write_text(''.join(f"file '{index}.png'\nduration 12\n" for index in range(len(slides)))
                            + f"file '{len(slides)-1}.png'\n")
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0',
                        '-i', str(manifest), '-t', '60', '-r', '24', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                        str(output / 'demo-video.mp4')], check=True, timeout=120)
        # Keep the final frame for a quick visual check without a video player.
        shutil.copyfile(directory / '4.png', output / 'demo-video-poster.png')
    (output / 'walkthrough-result.json').write_text(json.dumps(report, indent=2) + '\n')
    subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_name,width,height',
                    '-of', 'json', str(output / 'demo-video.mp4')], check=True)
    print('Recorded real FalkorDB answers; wrote a 60-second edited replay and full query evidence.')


if __name__ == '__main__':
    main()
