export function Logo({ height = 34 }: { height?: number }) {
  return (<>
    <img className="logo-light" src="/brand/logo.svg" alt="FlatWise" height={height} style={{ height, width: "auto" }} />
    <img className="logo-dark" src="/brand/logo-white.svg" alt="FlatWise" height={height} style={{ height, width: "auto" }} />
  </>);
}
