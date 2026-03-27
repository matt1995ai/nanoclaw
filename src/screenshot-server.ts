/**
 * Lightweight HTTP server for receiving screenshots from the Chrome extension.
 * Injects them into nanoclaw's message pipeline as image messages.
 */
import { createServer, IncomingMessage, Server, ServerResponse } from 'http';

import { logger } from './logger.js';
import { storeMessage } from './db.js';

const MAX_BODY_SIZE = 20 * 1024 * 1024; // 20MB

function readBody(req: IncomingMessage): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    req.on('data', (chunk: Buffer) => {
      size += chunk.length;
      if (size > MAX_BODY_SIZE) {
        req.destroy();
        reject(new Error('Body too large'));
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

function cors(res: ServerResponse): void {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}

export function startScreenshotServer(
  port: number,
  host: string,
  chatJid: string,
): Promise<Server> {
  return new Promise((resolve, reject) => {
    const server = createServer(async (req, res) => {
      cors(res);

      if (req.method === 'OPTIONS') {
        res.writeHead(204);
        res.end();
        return;
      }

      if (req.method !== 'POST' || req.url !== '/screenshot') {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Not found' }));
        return;
      }

      try {
        const body = await readBody(req);
        const data = JSON.parse(body.toString());

        if (!data.image || typeof data.image !== 'string') {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Missing image field (base64)' }));
          return;
        }

        // Strip data URL prefix if present (e.g., "data:image/png;base64,...")
        let base64 = data.image;
        let mediaType = 'image/png';
        const dataUrlMatch = base64.match(
          /^data:(image\/[a-z]+);base64,(.+)$/,
        );
        if (dataUrlMatch) {
          mediaType = dataUrlMatch[1];
          base64 = dataUrlMatch[2];
        }

        const caption = data.caption || '';
        const imageMarker = `[nc:image:${mediaType}:${base64}]`;
        const content = caption
          ? `${imageMarker} ${caption}`
          : `${imageMarker} [Screenshot from Chrome extension]`;

        const msgId = `screenshot-${Date.now()}`;
        storeMessage({
          id: msgId,
          chat_jid: chatJid,
          sender: 'chrome-extension',
          sender_name: 'M',
          content,
          timestamp: new Date().toISOString(),
          is_from_me: false,
        });

        logger.info(
          { msgId, size: base64.length },
          'Screenshot injected into message pipeline',
        );

        res.writeHead(201, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, id: msgId }));
      } catch (err) {
        logger.error({ err }, 'Screenshot server error');
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(
          JSON.stringify({
            error: err instanceof Error ? err.message : 'Internal error',
          }),
        );
      }
    });

    server.listen(port, host, () => {
      logger.info({ port, host }, 'Screenshot server started');
      resolve(server);
    });

    server.on('error', reject);
  });
}
