// contracts/*.schema.json → src/api/contract-types.d.ts 재생성.
// 계약이 타입 SSOT(§15.1) — 스키마 변경 시 `npm run gen:types`로 drift 0 유지.
// 참고: 현재 src/api/types.ts는 손번역본(즉시 컴파일용). 이 스크립트는 검증/대조용
// 산출물(contract-types.d.ts)을 만들어, 손번역이 스키마와 어긋나지 않았는지 확인한다.

import { compileFromFile } from 'json-schema-to-typescript'
import { writeFile, mkdir } from 'node:fs/promises'
import { fileURLToPath, URL } from 'node:url'

const contractsDir = fileURLToPath(new URL('../../../contracts/', import.meta.url))
const outFile = fileURLToPath(new URL('../src/api/contract-types.d.ts', import.meta.url))

const schemas = ['finding.schema.json', 'attack-path.schema.json', 'case.schema.json']

let out = '// AUTO-GENERATED from contracts/*.schema.json — do not edit. (npm run gen:types)\n\n'
for (const s of schemas) {
  const ts = await compileFromFile(contractsDir + s, {
    bannerComment: '',
    additionalProperties: false,
    cwd: contractsDir, // $ref(finding.schema.json) 해소
  })
  out += ts + '\n'
}

await mkdir(fileURLToPath(new URL('../src/api/', import.meta.url)), { recursive: true })
await writeFile(outFile, out, 'utf8')
console.log('generated:', outFile)
