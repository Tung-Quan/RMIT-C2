/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Afacad Flux", "Montserrat", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Fraunces", "Afacad Flux", "serif"]
      }
    }
  },
  plugins: []
};
