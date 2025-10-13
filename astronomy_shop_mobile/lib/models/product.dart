import '../services/config_service.dart';

class Product {
  final String id;
  final String name;
  final String description;
  final double priceUsd;
  final String imageUrl;
  final List<String> categories;

  const Product({
    required this.id,
    required this.name,
    required this.description,
    required this.priceUsd,
    required this.imageUrl,
    required this.categories,
  });

  factory Product.fromJson(Map<String, dynamic> json) {
    double price = 0.0;
    if (json['priceUsd'] != null) {
      final priceData = json['priceUsd'] as Map<String, dynamic>;
      final units = (priceData['units'] as num?)?.toDouble() ?? 0.0;
      final nanos = (priceData['nanos'] as num?)?.toDouble() ?? 0.0;
      price = units + (nanos / 1000000000);
    }
    List<String> categoryList = [];
    if (json['categories'] != null) {
      categoryList = (json['categories'] as List<dynamic>)
          .map((category) => category.toString())
          .toList();
    }
    final pictureFilename = json['picture']?.toString() ?? '';

    // Build image URL using the API base URL from config
    final config = ConfigService.instance;
    final baseUrl = config.apiBaseUrl.replaceAll('/api', '');
    final imageUrl = pictureFilename.isNotEmpty
        ? '$baseUrl/images/products/$pictureFilename'
        : '$baseUrl/images/products/default.jpg';

    return Product(
      id: json['id']?.toString() ?? '',
      name: json['name']?.toString() ?? 'Unknown Product',
      description: json['description']?.toString() ?? '',
      priceUsd: price,
      imageUrl: imageUrl,
      categories: categoryList,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'description': description,
      'priceUsd': {
        'currencyCode': 'USD',
        'units': priceUsd.floor(),
        'nanos': ((priceUsd - priceUsd.floor()) * 1000000000).round(),
      },
      'picture': imageUrl,
      'categories': categories,
    };
  }

  static List<Product> getHardcodedProducts() {
    return [
      const Product(
        id: 'OLJCESPC7Z',
        name: 'Vintage Telescope',
        description: 'This vintage telescope is perfect for watching the stars.',
        priceUsd: 89.99,
        imageUrl: '/images/products/telescope.jpg',
        categories: ['telescopes', 'vintage'],
      ),
      const Product(
        id: '66VCHSJNUP',
        name: 'Solar System Model',
        description: 'A detailed model of our solar system with all planets.',
        priceUsd: 124.50,
        imageUrl: '/images/products/solar-system.jpg',
        categories: ['models', 'educational'],
      ),
      const Product(
        id: '1YMWWN1N4O',
        name: 'Star Chart Poster',
        description: 'Beautiful poster showing constellations of the northern hemisphere.',
        priceUsd: 19.99,
        imageUrl: '/images/products/star-chart.jpg',
        categories: ['posters', 'educational'],
      ),
      const Product(
        id: 'L9ECAV7KIM',
        name: 'Astronaut Helmet Replica',
        description: 'Realistic replica of NASA astronaut helmet.',
        priceUsd: 299.99,
        imageUrl: '/images/products/astronaut-helmet.jpg',
        categories: ['replicas', 'collectibles'],
      ),
      const Product(
        id: '2ZYFJ3GM2N',
        name: 'Meteorite Sample',
        description: 'Genuine meteorite sample from outer space.',
        priceUsd: 79.99,
        imageUrl: '/images/products/meteorite.jpg',
        categories: ['specimens', 'rare'],
      ),
    ];
  }

  String get formattedPrice => '\$${priceUsd.toStringAsFixed(2)}';
  
  String getFormattedPrice([dynamic currencyService]) {
    if (currencyService != null && currencyService.selectedCurrency != null) {
      return currencyService.formatPrice(priceUsd);
    }
    return formattedPrice;
  }
  
  double getConvertedPrice([dynamic currencyService]) {
    if (currencyService != null && currencyService.selectedCurrency != null) {
      return currencyService.convertPrice(priceUsd);
    }
    return priceUsd;
  }
}