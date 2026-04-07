import type { ReactNode } from "react";

interface FeatureFrameProps {
  id: string;
  index: string;
  eyebrow: string;
  title: string;
  description: string;
  accentClassName: string;
  children: ReactNode;
}

export function FeatureFrame({
  id,
  index,
  eyebrow,
  title,
  description,
  accentClassName,
  children,
}: FeatureFrameProps) {
  return (
    <section id={id} className={`feature-frame ${accentClassName}`}>
      <div className="feature-header">
        <div>
          <p className="feature-index">{index}</p>
          <p className="feature-eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
          <p className="feature-description">{description}</p>
        </div>
      </div>
      <div className="feature-body">{children}</div>
    </section>
  );
}
