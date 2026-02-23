// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation

import com.amazon.vincent.job.annotation.vcf.VCFAnnotationOptions
import spray.json._

case class TSVImportOptions(readOptions: Option[Map[String, String]])

case class TSVStoreOptions(
    annotationType: Option[String],
    formatToHeader: Option[Map[String, String]],
    schema: Option[String])

case class AnnotationStoreOptions(tsvStoreOptions: Option[TSVStoreOptions])

case class FormatOptions(
    tsvOptions: Option[TSVImportOptions],
    vcfOptions: Option[VCFAnnotationOptions])

object FormatOptionsJsonProtocol extends DefaultJsonProtocol {
  implicit object AnyJsonFormat extends JsonFormat[Map[String, String]] {
    def read(value: JsValue): Map[String, String] = {
      val obj = value match {
        case x: JsObject =>
          x.fields.mapValues {
            case JsString(value) => value
            case JsTrue => "true"
            case JsFalse => "false"
            case boolean: JsBoolean => boolean.toString()
            case _ => throw DeserializationException("Expecting String or Boolean")
          }
        case _ =>
          throw DeserializationException("Expecting JsObject for Map[String, String] values")
      }
      obj
    }
    override def write(obj: Map[String, String]): JsValue = throw new NotImplementedError(
      "Not write is not implemented")
  }
  implicit val vcfAnnotationOptionsFormat: RootJsonFormat[VCFAnnotationOptions] = jsonFormat2(
    VCFAnnotationOptions)
  implicit val tsvImportOptions: RootJsonFormat[TSVImportOptions] = jsonFormat1(TSVImportOptions)
  implicit val formatOptionsFormat: RootJsonFormat[FormatOptions] = jsonFormat2(FormatOptions)
  implicit val tsvStoreOptions: RootJsonFormat[TSVStoreOptions] = jsonFormat3(TSVStoreOptions)
  implicit val annotationStoreOptions: RootJsonFormat[AnnotationStoreOptions] = jsonFormat1(
    AnnotationStoreOptions)
}
