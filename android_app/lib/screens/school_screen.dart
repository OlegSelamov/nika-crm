import 'package:flutter/material.dart';
import '../services/api_service.dart';

class SchoolScreen extends StatefulWidget {
  const SchoolScreen({super.key});
  @override State<SchoolScreen> createState()=>_SchoolScreenState();
}
class _SchoolScreenState extends State<SchoolScreen> with SingleTickerProviderStateMixin {
  late TabController tabs;
  @override void initState(){super.initState();tabs=TabController(length:2,vsync:this);}
  @override void dispose(){tabs.dispose();super.dispose();}
  @override Widget build(BuildContext context)=>Column(children:[
    TabBar(controller:tabs,tabs:const[Tab(text:'Питание',icon:Icon(Icons.restaurant_outlined)),Tab(text:'Классные руководители',icon:Icon(Icons.school_outlined))]),
    Expanded(child:TabBarView(controller:tabs,children:const[_MealsTab(),_LeadersTab()])),
  ]);
}

class _LeadersTab extends StatefulWidget { const _LeadersTab(); @override State<_LeadersTab> createState()=>_LeadersTabState(); }
class _LeadersTabState extends State<_LeadersTab>{
  List<dynamic> leaders=[]; bool loading=true;
  @override void initState(){super.initState();load();}
  Future<void> load()async{final d=await ApiService.schoolLeaders();if(mounted)setState((){leaders=List<dynamic>.from(d['leaders']??[]);loading=false;});}
  Future<void> edit([Map<String,dynamic>? row])async{
    final name=TextEditingController(text:row?['full_name']??'');final cls=TextEditingController(text:row?['class_name']??'');
    final room=TextEditingController(text:row?['room']??'');final phone=TextEditingController(text:row?['phone']??'');
    final ok=await showDialog<bool>(context:context,builder:(c)=>AlertDialog(title:Text(row==null?'Добавить':'Редактировать'),content:SingleChildScrollView(child:Column(mainAxisSize:MainAxisSize.min,children:[
      TextField(controller:name,decoration:const InputDecoration(labelText:'ФИО')),TextField(controller:cls,decoration:const InputDecoration(labelText:'Класс')),
      TextField(controller:room,decoration:const InputDecoration(labelText:'Кабинет')),TextField(controller:phone,decoration:const InputDecoration(labelText:'Телефон')),
    ])),actions:[TextButton(onPressed:()=>Navigator.pop(c,false),child:const Text('Отмена')),FilledButton(onPressed:()=>Navigator.pop(c,true),child:const Text('Сохранить'))]));
    if(ok==true){await ApiService.saveSchoolLeader({'full_name':name.text,'class_name':cls.text,'room':room.text,'phone':phone.text},id:row?['id']);await load();}
  }
  @override Widget build(BuildContext context){if(loading)return const Center(child:CircularProgressIndicator());return Scaffold(
    floatingActionButton:FloatingActionButton(onPressed:()=>edit(),child:const Icon(Icons.add)),
    body:RefreshIndicator(onRefresh:load,child:ListView.builder(padding:const EdgeInsets.all(12),itemCount:leaders.length,itemBuilder:(c,i){final r=Map<String,dynamic>.from(leaders[i]);return Card(child:ListTile(
      leading:const CircleAvatar(child:Icon(Icons.person_outline)),title:Text(r['full_name']??''),subtitle:Text('${r['class_name']??'Без класса'} • каб. ${r['room']??'—'}\n${r['phone']??''}'),
      isThreeLine:true,onTap:()=>edit(r),trailing:IconButton(icon:const Icon(Icons.delete_outline),onPressed:()async{await ApiService.deleteSchoolLeader(r['id']);await load();}),
    ));})),
  );}
}

class _MealsTab extends StatefulWidget{const _MealsTab();@override State<_MealsTab> createState()=>_MealsTabState();}
class _MealsTabState extends State<_MealsTab>{
  DateTime day=DateTime.now();List<dynamic> rows=[];Map<String,dynamic> totals={};bool loading=true;
  String get ds=>'${day.year.toString().padLeft(4,'0')}-${day.month.toString().padLeft(2,'0')}-${day.day.toString().padLeft(2,'0')}';
  @override void initState(){super.initState();load();}
  Future<void> load()async{setState(()=>loading=true);final d=await ApiService.schoolMeals(ds);if(mounted)setState((){rows=List<dynamic>.from(d['rows']??[]);totals=Map<String,dynamic>.from(d['totals']??{});loading=false;});}
  Future<void> edit(Map<String,dynamic> r)async{
    final plan=TextEditingController(text='${r['plan_count']??0}'),fact=TextEditingController(text:'${r['fact_count']??0}');
    final free=TextEditingController(text:'${r['free_count']??0}'),paid=TextEditingController(text:'${r['paid_count']??0}'),note=TextEditingController(text:r['note']??'');
    final ok=await showDialog<bool>(context:context,builder:(c)=>AlertDialog(title:Text(r['class_name']??'Класс'),content:SingleChildScrollView(child:Column(children:[
      TextField(controller:plan,keyboardType:TextInputType.number,decoration:const InputDecoration(labelText:'План')),TextField(controller:fact,keyboardType:TextInputType.number,decoration:const InputDecoration(labelText:'Факт')),
      TextField(controller:free,keyboardType:TextInputType.number,decoration:const InputDecoration(labelText:'Бесплатное')),TextField(controller:paid,keyboardType:TextInputType.number,decoration:const InputDecoration(labelText:'Платное')),
      TextField(controller:note,decoration:const InputDecoration(labelText:'Примечание')),
    ])),actions:[TextButton(onPressed:()=>Navigator.pop(c,false),child:const Text('Отмена')),FilledButton(onPressed:()=>Navigator.pop(c,true),child:const Text('Сохранить'))]));
    if(ok==true){await ApiService.saveSchoolMeals({'date':ds,'rows':[{'class_id':r['class_id'],'plan_count':int.tryParse(plan.text)??0,'fact_count':int.tryParse(fact.text)??0,'free_count':int.tryParse(free.text)??0,'paid_count':int.tryParse(paid.text)??0,'note':note.text}]});await load();}
  }
  @override Widget build(BuildContext context)=>Column(children:[
    Padding(padding:const EdgeInsets.all(12),child:Row(children:[IconButton(onPressed:(){day=day.subtract(const Duration(days:1));load();},icon:const Icon(Icons.chevron_left)),Expanded(child:OutlinedButton.icon(onPressed:()async{final d=await showDatePicker(context:context,initialDate:day,firstDate:DateTime(2024),lastDate:DateTime(2035));if(d!=null){day=d;load();}},icon:const Icon(Icons.calendar_today_outlined),label:Text(ds))),IconButton(onPressed:(){day=day.add(const Duration(days:1));load();},icon:const Icon(Icons.chevron_right))])),
    Padding(padding:const EdgeInsets.symmetric(horizontal:12),child:Card(child:Padding(padding:const EdgeInsets.all(12),child:Wrap(spacing:16,runSpacing:8,children:[Text('План: ${totals['plan']??0}'),Text('Факт: ${totals['fact']??0}'),Text('Бесплатно: ${totals['free']??0}'),Text('Платно: ${totals['paid']??0}')])))),
    Expanded(child:loading?const Center(child:CircularProgressIndicator()):RefreshIndicator(onRefresh:load,child:ListView.builder(padding:const EdgeInsets.all(12),itemCount:rows.length,itemBuilder:(c,i){final r=Map<String,dynamic>.from(rows[i]);return Card(child:ListTile(
      title:Text(r['class_name']??''),subtitle:Text('${r['leader_name']??'Без руководителя'}\nПлан ${r['plan_count']} • Факт ${r['fact_count']} • Бесплатно ${r['free_count']} • Платно ${r['paid_count']}'),isThreeLine:true,onTap:()=>edit(r),trailing:const Icon(Icons.edit_outlined),
    ));}))),
  ]);
}
