export type ImageAttribution = {
  asset: string
  work: string
  author: string
  sourceUrl: string
  license: string
  licenseUrl: string
  modificationKey: string
  aliases: string[]
}

export const IMAGE_ATTRIBUTIONS: ImageAttribution[] = [
  {
    asset: 'RTX2060.jpg',
    work: 'NVIDIA GeForce RTX 2060',
    author: 'Mr ATM',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:NVIDIA_GeForce_RTX_2060.jpg',
    license: 'CC BY 2.0',
    licenseUrl: 'https://creativecommons.org/licenses/by/2.0/',
    modificationKey: 'imageAttributionsCropResize',
    aliases: ['RTX 2070', 'RTX 2070 SUPER'],
  },
  {
    asset: 'RTX3070.jpg',
    work: 'MSI GeForce RTX 3070 VENTUS 3X OC',
    author: 'TheStriker',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:MSI_GeForce_RTX_3070_VENTUS_3X_OC.jpg',
    license: 'CC BY 4.0',
    licenseUrl: 'https://creativecommons.org/licenses/by/4.0/',
    modificationKey: 'imageAttributionsCropResize',
    aliases: ['RTX 3050', 'RTX 3060', 'RTX 3060 Ti', 'RTX 3070 Ti'],
  },
  {
    asset: 'RTX4070.jpg',
    work: '2023 Gigabyte GeForce RTX 4070 Aero OC 12GB (4)',
    author: 'Jacek Halicki',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:2023_Gigabyte_GeForce_RTX_4070_Aero_OC_12GB_(4).jpg',
    license: 'CC BY-SA 4.0',
    licenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
    modificationKey: 'imageAttributionsCropResizeShareAlike',
    aliases: ['RTX 4060', 'RTX 4060 Ti', 'RTX 4070 SUPER', 'RTX 4070 Ti'],
  },
  {
    asset: 'RTX5060Ti.jpg',
    work: 'Nvidia GeForce RTX 5060 Ti 16GB, PNY Overclocked Dual Fan, front',
    author: 'FreeMediaKid!',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:Nvidia_GeForce_RTX_5060_Ti_16GB,_PNY_Overclocked_Dual_Fan,_front.jpg',
    license: 'CC BY-SA 4.0',
    licenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
    modificationKey: 'imageAttributionsCropResizeShareAlike',
    aliases: ['RTX 5060'],
  },
  {
    asset: 'RTX5070.jpg',
    work: '20260521 ASUS RTX 5070 graphics card',
    author: 'Striker9498',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:20260521_%EC%95%84%EC%88%98%EC%8A%A4_RTX5070_%EA%B7%B8%EB%9E%98%ED%94%BD%EC%B9%B4%EB%93%9C.jpg',
    license: 'CC0 1.0',
    licenseUrl: 'https://creativecommons.org/publicdomain/zero/1.0/',
    modificationKey: 'imageAttributionsCropResize',
    aliases: ['RTX 5070 Ti'],
  },
  {
    asset: 'RTX5080.jpg',
    work: 'RTX 5080',
    author: 'XD7006',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:RTX_5080.png',
    license: 'CC BY 4.0',
    licenseUrl: 'https://creativecommons.org/licenses/by/4.0/',
    modificationKey: 'imageAttributionsCropConvert',
    aliases: [],
  },
]
