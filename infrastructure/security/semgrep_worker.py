"""Start installed Semgrep without caller-controlled scanner configuration."""
import os

if __name__ == '__main__':
    for name in list(os.environ):
        if name.startswith('SEMGREP_') or name in {'OTEL_EXPORTER_OTLP_ENDPOINT', 'OTEL_EXPORTER_OTLP_TRACES_ENDPOINT'}:
            del os.environ[name]
    from semgrep.console_scripts.pysemgrep import main
    main()
