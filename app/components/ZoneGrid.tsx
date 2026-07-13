export const zones = ["NW", "N", "NE", "W", "C", "E", "SW", "S", "SE"] as const;

export type Zone = (typeof zones)[number];

export type ZoneGridItem = {
  slot: string;
  zone: Zone;
};

type ZoneGridProps = {
  items: ZoneGridItem[];
};

export function ZoneGrid({ items }: ZoneGridProps) {
  return (
    <div className="zone-grid" aria-label="3 by 3 Vastu zone grid">
      {zones.map((zone) => {
        const zoneItems = items.filter((item) => item.zone === zone);
        return (
          <div className={zoneItems.length ? "zone-cell occupied" : "zone-cell"} key={zone}>
            <strong>{zone}</strong>
            {zoneItems.length ? (
              <div className="zone-chip-list">
                {zoneItems.map((item) => (
                  <span className="zone-chip" key={`${zone}-${item.slot}`}>
                    {item.slot}
                  </span>
                ))}
              </div>
            ) : (
              <span>Open</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
