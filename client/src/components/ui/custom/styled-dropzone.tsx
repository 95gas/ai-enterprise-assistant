import Dropzone, { DropzoneProps } from 'react-dropzone';
import {File, FileText, Upload } from 'lucide-react';
import { ReactNode } from 'react';
import { Plural, Trans } from '@lingui/react/macro';

export function FiletypeIcon({ type }: { type: string }) {
  switch (type) {
    case type.match(/^application\/.*/)?.input:
      return <FileText className="w-4 h-4 mr-2" />

    default:
      return <File className="w-4 h-4 mr-2" />
  }
}

export function HumanReadableFileSize({ size }: { size: number }) {
  const i = size == 0 ? 0 : Math.floor(Math.log(size) / Math.log(1000))
  return (
    <>
      {+((size / Math.pow(1000, i)).toFixed(2)) * 1 + ' ' + ['B', 'kB', 'MB', 'GB', 'TB'][i]}
    </>
  )
}

export function StyledDropzone({ value, onDrop, accept, renderFile }: {
  value: File[]
  onDrop: DropzoneProps["onDrop"]
  accept: DropzoneProps["accept"]
  renderFile?: (file: File, index: number) => ReactNode
}) {
  return (
    <div className="space-y-4">
      <Dropzone onDrop={onDrop} accept={accept}>
        {({getRootProps, getInputProps}) => (
          <div {...getRootProps()} className="w-full border border-dashed p-4 rounded-md bg-muted/40 hover:bg-muted flex justify-center">
            <input {...getInputProps()} />
            <div className="flex flex-col items-center space-y-1 text-muted-foreground text-sm">
              <Upload className="w-4 h-4"/>
              <p>
                <Trans>
                  Upload your files by dragging them here or clicking to browse your files.
                  <Plural
                    value={value.length}
                    _0={""}
                    other={". Will reset the current selection"}
                  />
                </Trans>
              </p>
            </div>
          </div>
        )}
      </Dropzone>
      {value.length > 0 && (
        <ul className="flex flex-col space-y-2">
         {value?.map((f, index) => (
            <li key={f.name}>
              {(renderFile && renderFile(f, index)) ?? (
                <div className="text-sm flex items-center border rounded-md p-2">
                  <FiletypeIcon type={f.type} />
                  {f.name}
                  <span className="ml-auto">
                    <HumanReadableFileSize size={f.size} />
                  </span>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}