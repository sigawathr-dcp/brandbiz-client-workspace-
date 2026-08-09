import React from 'react'

export interface IconProps {
  size?: number
  className?: string
  style?: React.CSSProperties
  strokeWidth?: number
}

type IconDef = (props: IconProps) => React.ReactElement

function mk(children: React.ReactNode): IconDef {
  return ({ size = 16, className, style, strokeWidth = 1.7 }) => (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

export const Ic = {
  // ── Reference-matched icons (lowercase naming for new components) ──
  shield:   mk(<path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z"/>),
  lock:     mk(<><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></>),
  eye:      mk(<><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></>),
  send:     mk(<path d="M5 12h13M12 5l7 7-7 7"/>),
  plus:     mk(<path d="M12 5v14M5 12h14"/>),
  check:    mk(<path d="M5 12l5 5L19 7"/>),
  chevron:  mk(<path d="M6 9l6 6 6-6"/>),
  search:   mk(<><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></>),
  info:     mk(<><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5v.5"/></>),
  alert:    mk(<><path d="M12 3l9 16H3l9-16z"/><path d="M12 10v4M12 17v.5"/></>),
  x:        mk(<path d="M6 6l12 12M18 6L6 18"/>),
  message:  mk(<path d="M21 12a8 8 0 0 1-8 8H5l-2 2V12a8 8 0 0 1 16 0z"/>),
  database: mk(<><ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.66 3.58 3 8 3s8-1.34 8-3V6M4 12v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6"/></>),
  sliders:  mk(<><path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2.4"/><circle cx="8" cy="17" r="2.4"/></>),
  users:    mk(<><circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/><path d="M16 5.2A3.2 3.2 0 0 1 16 11M21 20c0-2.6-1.4-4.4-3.5-5"/></>),
  globe:    mk(<><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.5 2.5 15 0 18M12 3c-2.5 2.5-2.5 15 0 18"/></>),
  cpu:      mk(<><rect x="7" y="7" width="10" height="10" rx="2"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/></>),
  clock:    mk(<><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/></>),
  layers:   mk(<><path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 13l9 5 9-5"/></>),
  upload:   mk(<><path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></>),
  file:     mk(<><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></>),
  dollar:   mk(<><path d="M12 3v18"/><path d="M16.5 7.5c0-1.7-2-3-4.5-3s-4.5 1.3-4.5 3 2 3 4.5 3 4.5 1.3 4.5 3-2 3-4.5 3-4.5-1.3-4.5-3"/></>),
  grid:     mk(<><rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/></>),
  spark:    mk(<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M18 6l-2.5 2.5M8.5 15.5L6 18"/>),
  play:     mk(<polygon points="5 3 19 12 5 21 5 3" fill="currentColor" stroke="none"/>),
  back:     mk(<path d="M19 12H5M11 18l-6-6 6-6"/>),
  pin:      mk(<path d="M9 4h6l-1 7 3 3H7l3-3-1-7z M12 17v3"/>),
  trash:    mk(<><path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13"/></>),
  download: mk(<><path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 20h16"/></>),
  pencil:   mk(<path d="M16.5 3.5l4 4L8 20l-5 1 1-5L16.5 3.5z"/>),

  // ── PascalCase aliases for backward compatibility ──
  get Home()           { return mk(<><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></>) },
  get MessageSquare()  { return this.message },
  get Users()          { return this.users },
  get User()           { return mk(<><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></>) },
  get Shield()         { return this.shield },
  get FileText()        { return mk(<><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></>) },
  get Eye()            { return this.eye },
  get EyeOff()         { return mk(<><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></>) },
  get BarChart2()      { return mk(<><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></>) },
  get Settings()       { return mk(<><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></>) },
  get LogOut()         { return mk(<><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></>) },
  get Plus()           { return this.plus },
  get Send()           { return this.send },
  get Search()         { return this.search },
  get Download()       { return this.download },
  get Copy()           { return mk(<><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></>) },
  get Check()          { return this.check },
  get X()              { return this.x },
  get AlertTriangle()  { return mk(<><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></>) },
  get AlertCircle()    { return mk(<><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></>) },
  get Info()           { return this.info },
  get CheckCircle()    { return mk(<><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></>) },
  get XCircle()        { return mk(<><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></>) },
  get ChevronDown()    { return this.chevron },
  get ChevronRight()   { return mk(<polyline points="9 18 15 12 9 6"/>) },
  get ChevronLeft()    { return mk(<polyline points="15 18 9 12 15 6"/>) },
  get ChevronUp()      { return mk(<polyline points="18 15 12 9 6 15"/>) },
  get Sun()            { return mk(<><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></>) },
  get Moon()           { return mk(<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>) },
  get Lock()           { return this.lock },
  get Unlock()         { return mk(<><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></>) },
  get Sliders()        { return this.sliders },
  get Layers()         { return this.layers },
  get Cpu()            { return this.cpu },
  get Globe()          { return this.globe },
  get Menu()           { return mk(<><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></>) },
  get ArrowLeft()      { return mk(<><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></>) },
  get ArrowRight()     { return mk(<><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></>) },
  get Clock()          { return this.clock },
  get Zap()            { return mk(<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>) },
  get TrendingUp()     { return mk(<><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></>) },
  get Database()       { return this.database },
  get Filter()         { return mk(<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>) },
  get RefreshCw()      { return mk(<><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></>) },
  get Key()            { return mk(<path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>) },
  get BookOpen()       { return mk(<><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></>) },
  get ExternalLink()   { return mk(<><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 0 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></>) },
  get Package()        { return mk(<><line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></>) },
  get Minus()          { return mk(<line x1="5" y1="12" x2="19" y2="12"/>) },
  get MoreHorizontal() { return mk(<><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></>) },
}

export type IconName = keyof typeof Ic

interface IconComponentProps extends IconProps {
  name: IconName | string
  stroke?: number
}

/** Generic icon component — accepts lowercase or PascalCase names. */
export default function Icon({ name, stroke, ...props }: IconComponentProps) {
  // Try exact key first, then PascalCase, then capitalized
  const key = (name as keyof typeof Ic)
  const renderer = Ic[key] ?? Ic[(name.charAt(0).toUpperCase() + name.slice(1)) as keyof typeof Ic]
  const sw = stroke ?? props.strokeWidth
  return renderer ? renderer({ ...props, strokeWidth: sw }) : null
}
