/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#f5fbef',
          100: '#e6f0db',
          200: '#cbe8b3',
          300: '#98db5c',
          400: '#76c950',
          500: '#4eac3f',
          600: '#3f8f34',
          700: '#306f29',
          800: '#255721',
          900: '#1b441a',
        },
        dark: {
          950: '#03110a',
          900: '#052014',
          800: '#0b2c1c',
          700: '#123823',
          600: '#1b4a2f',
        },
        accent: {
          50: '#f2fde6',
          100: '#e6f7cf',
          200: '#d2f3a8',
          300: '#b9eb82',
          400: '#98db5c',
          500: '#7ccc49',
          600: '#5fb63a',
          700: '#4eac3f',
          800: '#3d8a2f',
          900: '#2b6721',
        },
      },
    },
  },
  plugins: [],
}
