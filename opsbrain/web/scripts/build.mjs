import { copyFile, mkdir, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { assets, publicRoot, distRoot } from './files.mjs';

export async function build(output = distRoot) {
  await mkdir(output, { recursive: true });
  const unexpected = (await readdir(output)).filter(name => !assets.includes(name));
  if (unexpected.length) throw new Error('Unexpected output files. Use an empty output directory; build will not delete user files.');
  for (const name of assets) await copyFile(join(publicRoot, name), join(output, name));
  return assets;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const copied = await build();
  console.log(`Static build ready: ${copied.length} allowlisted assets in web/dist. No environment files or backend sources copied.`);
}
