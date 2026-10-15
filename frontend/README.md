# HemoVida - Frontend

React + Vite para Cloudflare Pages. La configuración completa está en el README de la raíz.

- Desarrollo: `npm ci` y `npm run dev` (puerto 3000, proxy local a Django en 8000).
- Verificación de tipos: `npm run lint`.
- Producción: configurar `VITE_API_URL` con la URL HTTPS de Render y ejecutar `npm run build`.
- Publicar el directorio `dist` en Cloudflare Pages.

No requiere Gemini ni credenciales de Supabase en el navegador.
