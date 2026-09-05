import 'package:flutter/material.dart';
import '../services/api_service.dart';
import 'package:qr_flutter/qr_flutter.dart';
import '../services/printer_service.dart';
import '../widgets/app_widgets.dart';

class CheckScreen extends StatefulWidget {
  final int saleId;
  final bool autoPrint;

  const CheckScreen({
    super.key,
    required this.saleId,
    this.autoPrint = false,
  });

  @override
  State<CheckScreen> createState() => _CheckScreenState();
}

class _CheckScreenState extends State<CheckScreen> {
  Map<String, dynamic>? sale;
  String? error;

  @override
  void initState() {
    super.initState();
    loadSale();
  }

  Future<void> loadSale() async {
    try {
      final data =
          await ApiService.getSale(
        widget.saleId,
      );

      if (mounted) {
        setState(() {
          sale = data;
        });
		
		if (widget.autoPrint) {
		  await PrinterService.autoPrintIfEnabled(data);
		}
		
      }
    } catch (e) {
      if (mounted) setState(() => error = readableError(e));
    }
  }

  String paymentName() {
    if (sale == null) return "";

    switch (sale!["sale_type"]) {
      case "cash":
        return "Наличные";

      case "card":
        return "Банковская карта";

	  case "kaspi":

	    if ((sale?["kaspi_method"] ?? "")
		    .toString()
		    .isNotEmpty) {
		  return "Kaspi QR";
	    }

	    return "Kaspi";

      default:
        return "Оплата";
    }
  }

  @override
  Widget build(BuildContext context) {
    if (error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Чек')),
        body: ScreenStateView(icon: Icons.receipt_long_outlined, title: 'Чек не загрузился', message: error!, onAction: () { setState(() => error = null); loadSale(); }),
      );
    }
    if (sale == null) {
      return const Scaffold(
        body: Center(
          child:
              CircularProgressIndicator(),
        ),
      );
    }

    final items =
        sale!["items"] as List;

    return Scaffold(
      appBar: AppBar(
		title: Text(
		  "Чек №${sale!["sale_number"] ?? sale!["id"]}",
		),
      ),
      body: SingleChildScrollView(
        child: Center(
          child: Container(
            width: 320,
            padding:
                const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment:
                  CrossAxisAlignment.start,
              children: [

				Center(
				  child: Text(
					sale!["company_name"] ?? "",
					textAlign: TextAlign.center,
					style: const TextStyle(
					  fontSize: 20,
					  fontWeight: FontWeight.bold,
					),
				  ),
				),

				const SizedBox(height: 8),

				Center(
				  child: Text(
					"БИН/ИИН: ${sale!["company_bin"] ?? ""}",
					textAlign: TextAlign.center,
				  ),
				),

				const SizedBox(height: 4),

				Center(
				  child: Text(
					sale!["company_address"] ?? "",
					textAlign: TextAlign.center,
				  ),
				),

				const SizedBox(height: 12),

				const Divider(
				  thickness: 2,
				),
				
                const SizedBox(height: 4),

				Row(
				  mainAxisAlignment:
					  MainAxisAlignment.spaceBetween,
				  children: [

					Text(
					  "Чек №${sale!["sale_number"] ?? sale!["id"]}",
					  style: const TextStyle(
						fontWeight: FontWeight.bold,
						fontSize: 18,
					  ),
					),

					Text(
					  sale!["check_date"] ?? "",
					  style: const TextStyle(
						fontSize: 16,
					  ),
					),
				  ],
				),
				
				if ((sale!["rekassa_ticket_number"] ?? "")
					.toString()
					.isNotEmpty) ...[

				  const SizedBox(height: 10),

				  Row(
					mainAxisAlignment:
						MainAxisAlignment.spaceBetween,
					children: [
					  Text(
						"Продажа №${sale!["rekassa_document_number"] ?? "-"}",
					  ),
					  Text(
						"Смена ${sale!["rekassa_shift_number"] ?? "-"}",
					  ),
					],
				  ),

				  Row(
					mainAxisAlignment:
						MainAxisAlignment.spaceBetween,
					children: [
					  const Text("ФП:"),
					  Text(
						sale!["rekassa_ticket_number"]
							.toString(),
					  ),
					],
				  ),

				  Row(
					mainAxisAlignment:
						MainAxisAlignment.spaceBetween,
					children: [
					  const Text("РНМ:"),
					  Text(
						sale!["rekassa_rnm"]
							.toString(),
					  ),
					],
				  ),

				  Row(
					mainAxisAlignment:
						MainAxisAlignment.spaceBetween,
					children: [
					  const Text("ЗНМ:"),
					  Text(
						sale!["rekassa_znm"]
							.toString(),
					  ),
					],
				  ),

				  const Divider(),
				],

                const Divider(),

                ...items.map(
                  (item) => Padding(
                    padding:
                        const EdgeInsets.only(
                      bottom: 10,
                    ),
                    child: Column(
                      crossAxisAlignment:
                          CrossAxisAlignment
                              .start,
                      children: [

                        Text(
                          item["name"]
                              .toString(),
                          style:
                              const TextStyle(
                            fontWeight:
                                FontWeight
                                    .bold,
                          ),
                        ),

						Column(
						  crossAxisAlignment:
							  CrossAxisAlignment.start,
						  children: [

							Row(
							  mainAxisAlignment:
								  MainAxisAlignment.spaceBetween,
							  children: [

								Expanded(
								  child: Text(
									"${item["quantity"]} ${item["unit"]} × ${item["price"]}",
								  ),
								),

								Text(
								  "${item["total"]} ₸",
								),
							  ],
							),

							const SizedBox(height: 4),

							if ((item["gtin"] ?? "")
								.toString()
								.isNotEmpty)
							  Text(
								"GTIN: ${item["gtin"]}",
								style: const TextStyle(
								  fontSize: 12,
								),
							  ),

							if ((item["ntin"] ?? "")
								.toString()
								.isNotEmpty)
							  Text(
								"NTIN: ${item["ntin"]}",
								style: const TextStyle(
								  fontSize: 12,
								),
							  ),
						  ],
						)
                      ],
                    ),
                  ),
                ),

                const Divider(),

				Row(
				  mainAxisAlignment:
					  MainAxisAlignment.spaceBetween,
				  children: [

					const Text(
					  "ИТОГО",
					  style: TextStyle(
						fontSize: 22,
						fontWeight: FontWeight.bold,
					  ),
					),

					Text(
					  "${sale!["total_amount"]} ₸",
					  style: const TextStyle(
						fontSize: 22,
						fontWeight: FontWeight.bold,
					  ),
					),
				  ],
				),

				const SizedBox(height: 12),

				Row(
				  mainAxisAlignment:
					  MainAxisAlignment.spaceBetween,
				  children: [

					const Text("Оплачено"),

					Text(
					  "${sale!["paid_amount"]} ₸",
					),
				  ],
				),

				Row(
				  mainAxisAlignment:
					  MainAxisAlignment.spaceBetween,
				  children: const [

					Text("Сдача"),

					Text("0 ₸"),
				  ],
				),

                const SizedBox(height: 10),

                Row(
                  mainAxisAlignment:
                      MainAxisAlignment
                          .spaceBetween,
                  children: [

                    const Text(
                      "Оплата",
                    ),

                    Text(
                      paymentName(),
                    ),
                  ],
                ),

                const SizedBox(height: 16),

				Center(
				  child: QrImageView(
					data: sale!["rekassa_qr"] ??
						"SALE-${sale!["id"]}",
					size: 140,
				  ),
				),

				const SizedBox(height: 12),

                const Center(
                  child: Text(
                    "Спасибо за покупку",
                  ),
                ),
				
				const SizedBox(height: 24),

				Row(
				  children: [

					Expanded(
					  child: ElevatedButton.icon(
						onPressed: () async {
 
						  final ok = await PrinterService.printSaleReceipt(sale!);

						  if (!mounted) return;

						  ScaffoldMessenger.of(context)
							  .showSnackBar(
							SnackBar(
							  content: Text(
								ok
									? "Чек отправлен на печать"
									: "Ошибка печати",
							  ),
							),
						  );
						},
						icon: const Icon(Icons.print),
						label: const Text("Печать"),
						style: ElevatedButton.styleFrom(
						  minimumSize: const Size(0, 52),
						  shape: RoundedRectangleBorder(
							borderRadius: BorderRadius.circular(12),
						  ),
						),
					  ),
					),

					const SizedBox(width: 8),

					Expanded(
					  child: ElevatedButton.icon(
						onPressed: () {
						  // pdf
						},
						icon: const Icon(
						  Icons.picture_as_pdf,
						),
						label: const Text("PDF"),
						style: ElevatedButton.styleFrom(
						  minimumSize: const Size(
							0,
							52,
						  ),
						  shape: RoundedRectangleBorder(
							borderRadius:
								BorderRadius.circular(12),
						  ),
						),
					  ),
					),
				  ],
				),

				const SizedBox(height: 8),

				SizedBox(
				  width: double.infinity,
				  child: ElevatedButton.icon(
					onPressed: () {
					  // отправить
					},
					icon: const Icon(Icons.share),
					label: const Text(
					  "Отправить чек",
					),
					style: ElevatedButton.styleFrom(
					  minimumSize: const Size(
						0,
						52,
					  ),
					  shape: RoundedRectangleBorder(
						borderRadius:
							BorderRadius.circular(12),
					  ),
					),
				  ),
				),
              ],
            ),
          ),
        ),
      ),
    );
  }
  
  String buildPrintText() {
    if (sale == null) return "";

    final buffer = StringBuffer();

    buffer.writeln(
      sale!["company_name"] ?? "",
    );

    buffer.writeln(
      "ИИН/БИН: ${sale!["company_bin"] ?? ""}",
    );

    buffer.writeln(
      sale!["company_address"] ?? "",
    );

    buffer.writeln("");

    buffer.writeln(
      "Чек №${sale!["sale_number"] ?? sale!["id"]}",
    );
	
	if ((sale!["rekassa_ticket_number"] ?? "")
		.toString()
		.isNotEmpty) {

	  buffer.writeln("");

	  buffer.writeln(
	    "Продажа: №${sale!["rekassa_document_number"] ?? "-"}"
		    .padRight(18) +
	    "Смена: ${sale!["rekassa_shift_number"] ?? "-"}"
	  );

	  buffer.writeln(
		"ФП: ${sale!["rekassa_ticket_number"] ?? ""}"
	  );

	  buffer.writeln(
		"РНМ: ${sale!["rekassa_rnm"] ?? ""}"
	  );

	  buffer.writeln(
		"ЗНМ: ${sale!["rekassa_znm"] ?? ""}"
	  );

	  buffer.writeln("");
	}

    buffer.writeln(
      sale!["check_date"] ?? sale!["created_at"] ?? "",
    );

    buffer.writeln("");

    buffer.writeln(
      "------------------------------",
    );

	final items = sale!["items"] as List;

	for (final item in items) {
	  buffer.writeln(
		item["name"] ?? "",
	  );

	  buffer.writeln(
		"${item["quantity"]} ${item["unit"] ?? "шт"} x ${item["price"]} = ${item["total"]} ₸",
	  );

	  buffer.writeln("");
	}

    buffer.writeln("");

    buffer.writeln(
      "ИТОГО: ${sale!["total_amount"]} ₸",
    );

    buffer.writeln("");

    buffer.writeln(
      "Оплата: ${paymentName()}",
    );

    buffer.writeln("");

    buffer.writeln(
      "Спасибо за покупку",
    );

    buffer.writeln("");
    buffer.writeln("");
    buffer.writeln("");

    return buffer.toString();
  }
}
