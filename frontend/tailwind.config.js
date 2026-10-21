/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "Arial", "sans-serif"] },
      colors: {
        ink: { DEFAULT: "var(--text-primary)", 2: "var(--text-secondary)", 3: "var(--text-muted)" },
        surface: { DEFAULT: "var(--surface-1)", 2: "var(--surface-2)", 3: "var(--surface-3)" },
        line: "var(--line)",
        accent: { DEFAULT: "var(--accent)", ink: "var(--accent-ink)" },
      },
    },
  },
  plugins: [],
};
