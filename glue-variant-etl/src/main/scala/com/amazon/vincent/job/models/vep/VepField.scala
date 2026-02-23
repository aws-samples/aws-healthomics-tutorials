// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models.vep

import com.amazon.vincent.job.models.exceptions.VincentUserException
import htsjdk.variant.vcf.{VCFHeaderLineTranslator, VCFHeaderVersion}

import scala.collection.mutable.ArrayBuffer
import scala.util.{Failure, Success, Try}

sealed trait VepField

// Keeping this as a separate object instead of having it as a companion object so this method does not gets serialize in spark
object VepFieldGenerator {
  val vepFormatStartWord = "Format:"
  val vepFieldDelimiter = "\\|"
  val infoDescriptionKey = "Description"
  val vepDescriptionPrefix = "Consequence annotations from Ensembl VEP. Format:"

  def fromHeader(header: String): Option[Array[VepField]] = {
    val headerMap = Try {
      VCFHeaderLineTranslator.parseLine(VCFHeaderVersion.VCF4_3, header, null)
    } match {
      case Failure(exception) =>
        throw new VincentUserException(
          "VCF header is malformed. Please ensure header is as per specification.")
      case Success(value) => value
    }

    val description = headerMap.getOrDefault(infoDescriptionKey, "")
    if (!description.startsWith(vepDescriptionPrefix)) {
      return None
    }

    val order = ArrayBuffer[VepField]()

    val lastVal = description
      .split(vepFormatStartWord, 2)
      .last
      .trim

    lastVal
      .split(vepFieldDelimiter)
      .foreach { elem =>
        VepDefaultField.fromName(elem) match {
          case Some(value) => order.append(value)
          case None => order.append(ExtraField(elem.toLowerCase()))
        }
      }
    Some(order.toArray)
  }
}

/**
 * Used to represent a field in the VEP header. The name is the name of the format in the INFO
 * field header and should match defaults in
 * https://useast.ensembl.org/info/docs/tools/vep/vep_formats.html#vcfout
 *
 * These are serializable so that they can be be used with spark
 *
 * @param name:
 *   Name of VEP field
 */
sealed abstract class VepDefaultField(val name: String) extends VepField with Serializable

object VepDefaultField {
  case object Allele extends VepDefaultField("Allele")

  case object Consequence extends VepDefaultField("Consequence")

  case object Impact extends VepDefaultField("IMPACT")

  case object Symbol extends VepDefaultField("SYMBOL")

  case object Gene extends VepDefaultField("Gene")

  case object FeatureType extends VepDefaultField("Feature_type")

  case object Feature extends VepDefaultField("Feature")

  case object Biotype extends VepDefaultField("BIOTYPE")

  case object Exon extends VepDefaultField("EXON")

  case object Intron extends VepDefaultField("INTRON")

  case object Hgvsc extends VepDefaultField("HGVSc")

  case object Hgvsp extends VepDefaultField("HGVSp")

  case object CdnaPosition extends VepDefaultField("cDNA_position")

  case object CdsPosition extends VepDefaultField("CDS_position")

  case object ProteinPosition extends VepDefaultField("Protein_position")

  case object AminoAcids extends VepDefaultField("Amino_acids")

  case object Codons extends VepDefaultField("Codons")

  case object ExistingVariation extends VepDefaultField("Existing_variation")

  case object Distance extends VepDefaultField("DISTANCE")

  case object Strand extends VepDefaultField("STRAND")

  case object Flags extends VepDefaultField("FLAGS")

  case object SymbolSource extends VepDefaultField("SYMBOL_SOURCE")

  case object HgncId extends VepDefaultField("HGNC_ID")

  val values = Seq(
    Allele,
    Consequence,
    Impact,
    Symbol,
    Gene,
    FeatureType,
    Feature,
    Biotype,
    Exon,
    Intron,
    Hgvsc,
    Hgvsp,
    CdnaPosition,
    CdsPosition,
    ProteinPosition,
    AminoAcids,
    Codons,
    ExistingVariation,
    Distance,
    Strand,
    Flags,
    SymbolSource,
    HgncId)

  private val nameToField = values.map(x => x.name -> x).toMap

  def fromName(name: String): Option[VepField] = {
    nameToField.get(name)
  }
}

case class ExtraField(name: String) extends VepField
