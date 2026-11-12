/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Dark Theme Tokens
        dark: {
          bg: "#101820",
          sidebar: "#111A24",
          surface: "#18232E",
          card: "#18232E",
          cardElevated: "#202D39",
          elevated: "#202D39",
          border: "#303E4B",
          hover: "#223140",
          text: {
            primary: "#F1F4F7",
            secondary: "#A5B1BD",
            muted: "#7C8997",
          },
        },
        // Light Theme Tokens
        light: {
          bg: "#F4F6F8",
          sidebar: "#FFFFFF",
          surface: "#FFFFFF",
          card: "#FFFFFF",
          cardElevated: "#F8FAFB",
          secondary: "#F8FAFB",
          elevated: "#F8FAFB",
          border: "#DFE5EB",
          hover: "#EFF3F6",
          text: {
            primary: "#1C2835",
            secondary: "#536273",
            muted: "#7D8A99",
          },
        },
        // Direct surface and line tokens
        panel: "#18232E",
        panel2: "#202D39",
        line: "#303E4B",
        // Official Google / GDG Color System
        google: {
          blue: "#4285F4",
          red: "#EA4335",
          yellow: "#FBBC04",
          green: "#34A853",
        },
        gdg: {
          blue: "#4285F4",
          red: "#EA4335",
          yellow: "#FBBC04",
          green: "#34A853",
        },
        // Semantic neutral grey
        industrial: {
          50: "#F8FAFC",
          100: "#F1F5F9",
          200: "#E2E8F0",
          300: "#CBD5E1",
          400: "#94A3B8",
          500: "#64748B",
          600: "#475569",
          700: "#334155",
          800: "#1E293B",
          900: "#0F172A",
        },
      },
      fontFamily: {
        serif: ['"Times New Roman"', "Times", "serif"],
        sans: ['"Times New Roman"', "Times", "serif"],
        mono: ['"Times New Roman"', "Times", "serif"],
      },
      boxShadow: {
        subtle: "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
        card: "0 1px 3px 0 rgba(0, 0, 0, 0.08), 0 1px 2px -1px rgba(0, 0, 0, 0.04)",
        "dark-card": "0 1px 3px 0 rgba(0, 0, 0, 0.4), 0 1px 2px -1px rgba(0, 0, 0, 0.25)",
        elevated: "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.05)",
      },
    },
  },
  plugins: [],
};
