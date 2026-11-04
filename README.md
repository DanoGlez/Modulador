# Modulador

Voz de robot en vivo para Windows. El micrófono entra al programa, el efecto sale por un cable virtual y FiveM usa el otro extremo de ese cable como micrófono.

## FiveM

1. Instala [VB-Audio Cable](https://vb-audio.com/Cable/) y reinicia Windows.
2. Abre Modulador.
3. En **Micrófono**, elige el micro con el que hablas.
4. En **Salida hacia FiveM**, deja **CABLE Input**. Si sale varias veces, usa la de Windows WASAPI.
5. En **Escucharte**, elige tus auriculares si quieres oírte. Si lo dejas en **No escucharme**, FiveM igual recibe la voz.
6. Pulsa **Activar** y habla.
7. En Windows, abre Configuración, Sistema, Sonido, Entrada, y pon **CABLE Output**. En el mezclador de sonido clásico, marca también **CABLE Output** como dispositivo de comunicaciones.
8. En el servidor de FiveM, elige ese mismo **CABLE Output** como entrada de voz.

VoiceMeeter sirve igual: si la salida del modulador es **VoiceMeeter Input**, en FiveM el micrófono es **VoiceMeeter Output**.

Si FiveM sigue oyendo tu voz normal, el juego todavía tiene seleccionado el micrófono real. Cámbialo a **CABLE Output**.

## Escucha y acople

**Escucharte** manda una copia a los auriculares. FiveM no usa esa salida. Con auriculares el micrófono no vuelve a tomar el efecto. Si te escuchas por altavoces, la voz se acopla.

## Presets

- **Clásico**: robot grave, tipo ciencia ficción.
- **Cyborg**: más metálico y un poco triturado.
- **Radio**: voz estrecha y brillante.
- **8-bit**: voz cortada, casi cuadrada.

**Intensidad** mezcla tu voz con el efecto. **Frecuencia** es el tono que modula la voz. **Triturado** la recorta hasta dejarla a saltos.

## Generar el .exe

En Windows, con Python 3.11 o más nuevo, abre una terminal en esta carpeta y ejecuta `build.bat`. El programa queda en `dist\Modulador\Modulador.exe`.

## Probar sin empaquetar

```
python -m pip install -r requirements.txt
python -m app.main
```
