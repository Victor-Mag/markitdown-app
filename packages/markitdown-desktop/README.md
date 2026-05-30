# PDF para Markdown

Aplicativo desktop Windows para converter lotes de PDF em Markdown sem enviar
documentos ou conteudo pela rede. PDFs textuais usam o conversor `markitdown`.
Paginas com menos de 20 caracteres nao brancos usam OCR Tesseract local.

## Desenvolvimento

```powershell
python -m pip install -e ..\markitdown[pdf]
python -m pip install -e .
python -m unittest discover -s tests -v
python -m markitdown_desktop
```

## Binarios Tesseract

Os binarios nao ficam no repositorio. Antes do build, a TI deve copiar a
distribuicao Windows x64 aprovada para `resources/tesseract`, incluindo:

```text
tesseract.exe
*.dll
tessdata/por.traineddata
tessdata/eng.traineddata
licenses/
```

Depois, atualizar `resources/tesseract/checksums.sha256`. O build falha quando
um arquivo listado estiver ausente ou com checksum divergente.

## Dependencias aprovadas

Antes do release, a TI deve preencher `approved-requirements.lock` com as
versoes homologadas de todas as dependencias transitivas e seus hashes. O lock
deve incluir o PyInstaller. O build usa `pip --require-hashes` e falha quando o
lock ainda estiver vazio.

## Build Windows x64

Instale Python x64, Inno Setup 6 e execute:

```powershell
.\build.ps1
```

O script gera o executavel `--onedir` com PyInstaller e o instalador por usuario
em `dist-installer`. A assinatura corporativa deve ser aplicada aos artefatos
conforme o processo interno antes da distribuicao.
