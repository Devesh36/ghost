import captures from "../content/product-preview.json";
import { TabbedContent } from "./tabbed-content";
import { ArrowIcon } from "./icons";

export function ProductPreview() {
  return (
    <div className="product-window">
      <div className="product-window-bar">
        <span className="window-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span>ghost / demo-project</span>
        <span className="capture-label">EXECUTED SAMPLE</span>
      </div>
      <TabbedContent
        appearance="product"
        ariaLabel="Ghost product walkthrough"
        tabs={captures.map((capture) => ({
          id: `product-${capture.id}`,
          label: capture.label,
          content: (
            <figure>
              <figcaption>
                <span aria-hidden="true">$</span> {capture.command}
              </figcaption>
              <div
                className="product-output"
                role="region"
                aria-label={`${capture.label} terminal output`}
                tabIndex={0}
              >
                <pre
                  className="preview-wide"
                  dangerouslySetInnerHTML={{ __html: capture.wide }}
                />
                <pre
                  className="preview-compact"
                  dangerouslySetInnerHTML={{ __html: capture.compact }}
                />
              </div>
              <p className="product-evidence">{capture.note}</p>
            </figure>
          ),
        }))}
      />
      <div className="product-window-footer">
        <span>
          <span className="status-dot" /> local workspace
        </span>
        <a href="/docs#terminal-gallery">
          Full walkthrough <ArrowIcon />
        </a>
      </div>
    </div>
  );
}
