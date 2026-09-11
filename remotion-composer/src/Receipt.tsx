import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export interface ReceiptItem {
  name: string;
  price: string;
}

export interface ReceiptProps {
  shop?: string;
  tagline?: string;
  items?: ReceiptItem[];
  total?: string;
  cta?: string;
}

export const receiptDefaults: Required<ReceiptProps> = {
  shop: "HOSTAMAR AI TOOLS",
  tagline: "5 free coding tools — $0.00",
  items: [
    { name: "GitHub Copilot Free", price: "$0.00" },
    { name: "Kiro (AWS Claude)", price: "$0.00" },
    { name: "Antigravity (Google)", price: "$0.00" },
    { name: "Codex CLI + OpenRouter", price: "$0.00" },
    { name: "Kilo Code (no key)", price: "$0.00" },
  ],
  total: "$0.00",
  cta: "Comment NOCARD + Follow",
};

// Zero-key receipt explainer: dark backdrop, receipt paper unrolls,
// line items stamp in one by one, total pops with a spring.
export const Receipt: React.FC<ReceiptProps> = (props) => {
  const {
    shop = receiptDefaults.shop,
    tagline = receiptDefaults.tagline,
    items = receiptDefaults.items,
    total = receiptDefaults.total,
    cta = receiptDefaults.cta,
  } = props;
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const paperGrow = spring({ frame, fps, config: { damping: 18, stiffness: 90 } });
  const paperH = interpolate(paperGrow, [0, 1], [120, 1450]);

  return (
    <AbsoluteFill style={{ backgroundColor: "#0B0F0C" }}>
      {/* glow backdrop */}
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 50% 20%, rgba(14,124,58,0.35), transparent 60%)",
        }}
      />
      {/* receipt paper */}
      <div
        style={{
          position: "absolute",
          left: 90,
          top: 150,
          width: 900,
          height: paperH,
          overflow: "hidden",
          backgroundColor: "#FFFFFF",
          borderRadius: 18,
          padding: "48px 56px",
          fontFamily: "monospace",
          opacity: interpolate(frame, [0, 12], [0, 1]),
        }}
      >
        <div style={{ textAlign: "center", fontSize: 44, fontWeight: 900, color: "#111" }}>
          {shop}
        </div>
        <div style={{ textAlign: "center", fontSize: 26, color: "#0E7C3A", marginTop: 8 }}>
          {tagline}
        </div>
        <div style={{ borderTop: "3px dashed #111", margin: "28px 0" }} />
        {items.map((it, i) => {
          const start = 20 + i * 28;
          const o = interpolate(frame, [start, start + 14], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          const y = interpolate(frame, [start, start + 14], [24, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          return (
            <div
              key={i}
              style={{
                opacity: o,
                transform: `translateY(${y}px)`,
                display: "flex",
                justifyContent: "space-between",
                fontSize: 30,
                color: "#111",
                marginBottom: 18,
              }}
            >
              <span>{it.name}</span>
              <span style={{ fontWeight: 700 }}>{it.price}</span>
            </div>
          );
        })}
        <div style={{ borderTop: "3px dashed #111", margin: "28px 0" }} />
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: 44,
            fontWeight: 900,
            color: "#0E7C3A",
            transform: `scale(${spring({ frame: frame - 170, fps, config: { damping: 10, stiffness: 160 } })})`,
          }}
        >
          <span>TOTAL</span>
          <span>{total}</span>
        </div>
        <div style={{ textAlign: "center", fontSize: 28, color: "#111", marginTop: 30 }}>
          {cta}
        </div>
      </div>
    </AbsoluteFill>
  );
};
