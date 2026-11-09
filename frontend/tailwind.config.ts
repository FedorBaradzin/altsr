import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        space: "#05060B",
        space2: "#0A0C16",
        panel: "#121826",
        line: "rgba(130,150,210,.12)",
        ink: "#EAF0FF",
        muted: "#9AA6C4",
        dim: "#66708C",
        violet: "#8B5CF6",
        cyan: "#22D3EE",
        pass: "#34D399",
        review: "#FBBF24",
        block: "#F87171",
      },
      fontFamily: {
        sg: ['"Space Grotesk"', "sans-serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
