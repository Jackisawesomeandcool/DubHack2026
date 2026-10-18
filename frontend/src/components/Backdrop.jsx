// Page backdrop. The soft neutral theme uses one calm page color for every fit,
// so there is no per-fit palette or wipe transition anymore. Kept as a component
// so HaulCreator / GuestHaul don't need to change if a backdrop comes back.
export default function Backdrop() {
  return <div className="backdrop" aria-hidden="true" />;
}
