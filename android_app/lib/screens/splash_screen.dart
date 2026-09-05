import 'dart:async';

import 'package:flutter/material.dart';

import 'main_layout.dart';
import 'login_screen.dart';
import '../services/api_service.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() =>
      _SplashScreenState();
}

class _SplashScreenState
    extends State<SplashScreen> {

  @override
  void initState() {
    super.initState();
    start();
  }

  Future<void> start() async {

    await Future.delayed(const Duration(milliseconds: 650));

	final loggedIn =
		await ApiService.isLoggedIn();

    if (!mounted) return;

    Navigator.pushReplacement(
      context,
      MaterialPageRoute(
        builder: (_) =>
            loggedIn
                ? const MainLayout()
                : const LoginScreen(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {

    return Scaffold(

      backgroundColor:
          const Color(0xFF0B1F3A),

      body: Center(

        child: Column(

          mainAxisAlignment:
              MainAxisAlignment.center,

          children: [

            Image.asset(
              "assets/images/logo.png",
              height: 140,
            ),

            const SizedBox(
              height: 20,
            ),

            const Text(
              "Nika Business",
              style: TextStyle(
                color: Colors.white,
                fontSize: 30,
                fontWeight:
                    FontWeight.bold,
              ),
            ),

            const SizedBox(
              height: 8,
            ),

            const Text(
              "Учетная система\nдля бизнеса",
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white70,
                fontSize: 15,
              ),
            ),

            const SizedBox(
              height: 40,
            ),

            const CircularProgressIndicator(
              color: Colors.white,
            ),
          ],
        ),
      ),
    );
  }
}
