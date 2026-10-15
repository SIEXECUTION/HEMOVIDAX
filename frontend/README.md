# HemoVida - Frontend

React + Vite para Cloudflare Workers o Pages. La configuración completa está en el README de la raíz.

- Desarrollo: `npm ci` y `npm run dev` (puerto 3000, proxy local a Django en 8000).
- Verificación de tipos: `npm run lint`.
- Producción: ejecutar `npm run build`; usa `https://hemovidax.onrender.com` por defecto. `VITE_API_URL` permite cambiar la API y requiere recompilar.
- Publicar el directorio `dist` en Cloudflare Pages.
- En Workers, ejecutar `npx wrangler deploy` desde este directorio; `wrangler.jsonc` configura los assets y el fallback SPA. No requiere `_redirects`.

No requiere Gemini ni credenciales de Supabase en el navegador.
