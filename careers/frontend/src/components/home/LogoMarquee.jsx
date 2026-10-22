const logos = [
  { name: "Google", src: "/assets/brands/google.svg" },
  { name: "Intel", src: "/assets/brands/intel.svg" },
  { name: "Samsung", src: "/assets/brands/samsung.svg" },
  { name: "Nike", src: "/assets/brands/nike.svg" },
  { name: "Spotify", src: "/assets/brands/spotify.svg" },
  { name: "Airbnb", src: "/assets/brands/airbnb.svg" },
  { name: "Netflix", src: "/assets/brands/netflix.svg" },
  { name: "Apple", src: "/assets/brands/apple.svg" },
  { name: "Meta", src: "/assets/brands/meta.svg" },
  { name: "GitHub", src: "/assets/brands/github.svg" },
  { name: "Zoom", src: "/assets/brands/zoom.svg" },
  { name: "Figma", src: "/assets/brands/figma.svg" }
];

function LogoGroup({ hidden = false }) {
  return (
    <div className="logo-marquee__group" aria-hidden={hidden ? "true" : undefined}>
      {logos.map((logo) => (
        <span className="logo-marquee__item" key={logo.name}>
          <img src={logo.src} alt={hidden ? "" : logo.name} loading="lazy" />
        </span>
      ))}
    </div>
  );
}

export function LogoMarquee() {
  return (
    <section className="logo-marquee" id="companies" aria-labelledby="logo-marquee-title">
      <div className="logo-marquee__intro">
        <p className="homepage-eyebrow">Opportunity landscape</p>
        <h2 id="logo-marquee-title">Keep searches readable across the kinds of teams students already recognize.</h2>
      </div>
      <div className="logo-marquee__viewport" tabIndex={0}>
        <div className="logo-marquee__track">
          <LogoGroup />
          <LogoGroup hidden />
        </div>
      </div>
    </section>
  );
}
