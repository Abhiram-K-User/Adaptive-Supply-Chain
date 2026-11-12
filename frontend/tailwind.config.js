/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#080d19",
        panel: "#0f172a",
        panel2: "#16223b",
        line: "#243451"
      }
    }
  },
  plugins: []
};

