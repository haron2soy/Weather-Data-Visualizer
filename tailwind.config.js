/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html', // Adjust to match your template directory
    './static/**/*.js',     // Include JS files if you use Tailwind in JS
  ],
  theme: {
    extend: {}, // Add custom theme configurations here
  },
  plugins: [],
}